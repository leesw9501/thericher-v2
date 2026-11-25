import hashlib
import json
import subprocess
import time
from dataclasses import replace
from types import SimpleNamespace

import pytest

from thericher_v2.ops import h3_dec4_writer_census as w

_CID = "a" * 64
_FOREIGN = "b" * 64
_HOST = {"complete": True, "actors": [], "containers": []}


def _j(value):
    return json.dumps(value).encode() + b"\n"


def _snapshot(answers, *, owned=None):
    calls = []

    def invoke(argv):
        calls.append(argv)
        return next(answers)

    project = SimpleNamespace(
        template=lambda _: "invented",
        parse=lambda raw: [json.loads(line) for line in raw.splitlines()],
    )
    return w._collect(
        project,
        {"container_rules": []},
        invoke,
        own=owned,
        docker_args=("docker",),
        host_args=("host",),
    ), calls


def test_census_brackets_host_and_own_stopped_container_without_treating_it_running():
    replies = iter(
        [
            _FOREIGN.encode() + b"\n",
            _j(_HOST),
            _j({"Id": _CID, "Running": False}) + _j({"Id": _FOREIGN, "Running": True}),
            _FOREIGN.encode() + b"\n",
        ]
    )
    facts, calls = _snapshot(replies, owned=_CID)
    assert len(facts["containers"]) == 2 and calls[1] == ("host",)
    assert calls[2] == ("docker", "container", "inspect", "--format", "invented", _CID, _FOREIGN)
    assert calls[0] == calls[-1]


@pytest.mark.parametrize("broken", ["racing_membership", "omitted", "wrong_seen", "duplicate_host"])
def test_incomplete_or_changing_inventory_refuses(broken):
    cases = {
        "racing_membership": _j({"Id": _CID, "Running": True}),
        "omitted": b"",
        "wrong_seen": _j({"Id": _CID, "Running": False}),
        "duplicate_host": _j({"Id": _CID, "Running": True}),
    }
    host = (
        b'{"complete":true,"complete":true,"actors":[],"containers":[]}\n'
        if broken == "duplicate_host"
        else _j(_HOST)
    )
    with pytest.raises(ValueError):
        _snapshot(iter([_CID.encode() + b"\n", host, cases[broken], _FOREIGN.encode() + b"\n"]))


def test_read_only_tool_flags_keep_host_output_but_detach_docker(monkeypatch, tmp_path):
    before = time.monotonic() + 5
    calls = []

    def run(argv, **kwargs):
        calls.append((argv[0], kwargs["creationflags"]))
        assert kwargs["env"] == {} and kwargs["stderr"] == subprocess.DEVNULL
        return subprocess.CompletedProcess(argv, 0, b"invented")

    monkeypatch.setattr(w.subprocess, "run", run)
    for exe in (w._PWSH, w._DOCKER):
        assert w._run((str(exe),), cwd=tmp_path, env={}, deadline=before) == b"invented"
    assert calls == [
        (str(w._PWSH), getattr(subprocess, "CREATE_NO_WINDOW", 0)),
        (str(w._DOCKER), getattr(subprocess, "DETACHED_PROCESS", 0)),
    ]


def test_docker_desktop_aliases_keep_the_same_protected_write_root():
    root = r"D:\bank\protected"
    assert set(w._aliases((root,))) == {
        root,
        "d:/bank/protected",
        "/run/desktop/mnt/host/d/bank/protected",
        "/host_mnt/d/bank/protected",
        "/mnt/d/bank/protected",
    }
    assert w._windows_mount("D:") is None
    assert w._windows_mount("D:/") == "d:/"
    with pytest.raises(ValueError, match="mount_alias"):
        w._windows_mount("/run/desktop/mnt/host/d/bank/../protected")
    with pytest.raises(ValueError, match="mount_alias"):
        w._foreign_writable_binds(
            {
                "containers": [
                    {
                        "Id": _FOREIGN,
                        "Mounts": [
                            {"Type": "bind", "RW": True, "Source": "/unresolved/private"},
                        ],
                    }
                ]
            },
            _CID,
        )


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    if not all(path.is_file() for path in w._SOURCES):
        pytest.skip("retained source-census programs are available on the Paper host")
    claim = tmp_path / "claims.json"
    raw = _j(dict(host_rules=[], container_rules=[]))
    claim.write_bytes(raw)
    conf = tmp_path / "empty"
    conf.mkdir()
    p = w.Dec4CensusProfile(
        claim,
        hashlib.sha256(raw).hexdigest(),
        "1" * 64,
        "2" * 64,
        conf,
        ("invented-secret-root",),
        ("invented-bank",),
        ("3" * 64,),
    )
    monkeypatch.setattr(w, "_windows_root", lambda: tmp_path)
    monkeypatch.setattr(w, "_path_stamp", lambda _: (1234,))

    def pinned(path, pin, _stack):
        if path in (w._PWSH, w._DOCKER):
            return (1234,), None
        value = path.read_bytes()
        assert hashlib.sha256(value).hexdigest() == pin
        return (1234,), value

    monkeypatch.setattr(w, "_full_member", pinned)
    return p


def test_current_profile_pin_changes_for_policy_and_never_implicitly_accepts_actors(
    runtime, monkeypatch
):
    assert runtime.sha256 != replace(runtime, protected=("different-bank",)).sha256
    with pytest.raises(ValueError, match="h3_writer_census_profile"):
        replace(runtime, financial_entries=())
    guard = w.Dec4WriterCensus(runtime)
    host = dict(_HOST)

    def run(argv, **_):
        return _j(host) if argv[0] == str(w._PWSH) else b""

    monkeypatch.setattr(w, "_run", run)
    assert (
        guard.evaluate(
            own=None,
            deadline=time.monotonic() + 8,
            bind_owned=lambda _: frozenset(),
            exact_scope=None,
        )
        is True
    )
    host["actors"] = [dict(pid=4, start_ticks="1234", argv_sha256="9" * 64, children=[])]
    with pytest.raises(ValueError, match="^h3_writer_census_not_admitted$"):
        guard.evaluate(
            own=None,
            deadline=time.monotonic() + 8,
            bind_owned=lambda _: frozenset(),
            exact_scope=None,
        )


def test_owned_native_facts_must_still_match_after_the_scope_decision(runtime, monkeypatch):
    monkeypatch.setattr(w, "_run", lambda argv, **_: _j(_HOST) if argv[0] == str(w._PWSH) else b"")
    claims = iter((frozenset(), frozenset({(4, "5", "a" * 64)})))
    with pytest.raises(ValueError, match="^h3_writer_census_not_admitted$"):
        w.Dec4WriterCensus(runtime).evaluate(
            own=None,
            deadline=time.monotonic() + 8,
            bind_owned=lambda _: next(claims),
            exact_scope=None,
        )

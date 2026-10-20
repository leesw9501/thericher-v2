from __future__ import annotations

import json
import os
import socket
import stat
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from thericher_v2.research import engine_research_agent as agent
from thericher_v2.research.engine_research_agent import (
    GpuFileLock,
    GpuLockHeldError,
    GpuLockOwnershipError,
)


@pytest.fixture(autouse=True)
def deny_external_effects(monkeypatch):
    def denied(*_args, **_kwargs):
        pytest.fail("file-lock tests must not invoke a process or network operation")

    monkeypatch.setattr(subprocess, "Popen", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    for name in ("connect", "connect_ex", "bind", "listen"):
        monkeypatch.setattr(socket.socket, name, denied)


def assert_closed(fd: int) -> None:
    with pytest.raises(OSError):
        os.fstat(fd)


def different_payload(payload: bytes) -> bytes:
    record = json.loads(payload)
    token = record["owner_token"]
    record["owner_token"] = ("0" if token[0] != "0" else "1") + token[1:]
    return json.dumps(record, sort_keys=True).encode()


def test_lock_native_identity_schema_and_normal_cleanup(tmp_path):
    path = tmp_path / "locks" / "gpu.lock"
    lock = GpuFileLock(path)
    with lock as acquired:
        assert acquired is lock
        fd = lock._fd
        assert fd is not None
        info = os.fstat(fd)
        assert info.st_dev and info.st_ino
        assert (info.st_dev, info.st_ino) == (path.stat().st_dev, path.stat().st_ino)
        assert stat.S_ISREG(info.st_mode)
        assert not getattr(info, "st_file_attributes", 0) & 0x400
        record = json.loads(path.read_bytes())
        assert set(record) == {
            "schema_version",
            "agent",
            "pid",
            "created_at",
            "manual_recovery",
            "owner_token",
        }
        assert record["schema_version"] == agent.SCHEMA_VERSION
        assert record["agent"] == agent.AGENT_NAME
        assert record["pid"] == os.getpid()
        assert len(record["owner_token"]) == 32
        int(record["owner_token"], 16)
    assert not path.exists()
    assert_closed(fd)
    assert lock._fd is lock._identity is lock._payload is None


def test_lock_exception_cleanup_preserves_original_exception(tmp_path):
    path = tmp_path / "gpu.lock"
    with pytest.raises(ValueError, match="synthetic body failure"), GpuFileLock(path):
        raise ValueError("synthetic body failure")
    assert not path.exists()


def test_failed_enter_and_explicit_exit_preserve_winner(tmp_path):
    path = tmp_path / "gpu.lock"
    with GpuFileLock(path) as winner:
        original = path.read_bytes()
        loser = GpuFileLock(path)
        with pytest.raises(GpuLockHeldError):
            loser.__enter__()
        loser.__exit__()
        loser.__exit__()
        assert path.read_bytes() == original
        assert winner._fd is not None
        os.fstat(winner._fd)


@pytest.mark.parametrize("entered_before", [False, True])
def test_unacquired_or_second_exit_preserves_new_owner(tmp_path, entered_before):
    path = tmp_path / "gpu.lock"
    old = GpuFileLock(path)
    if entered_before:
        with old:
            pass
    with GpuFileLock(path) as winner:
        original = path.read_bytes()
        old.__exit__()
        assert path.read_bytes() == original
        assert winner._fd is not None
        os.fstat(winner._fd)


def test_reenter_same_instance_does_not_destroy_live_ownership(tmp_path):
    path = tmp_path / "gpu.lock"
    with GpuFileLock(path) as lock:
        original = path.read_bytes()
        with pytest.raises(RuntimeError, match="already entered"):
            lock.__enter__()
        assert path.read_bytes() == original
    assert not path.exists()


def test_same_inode_foreign_token_is_preserved_and_reported(tmp_path):
    path = tmp_path / "gpu.lock"
    lock = GpuFileLock(path).__enter__()
    fd = lock._fd
    assert fd is not None
    original_identity = path.stat().st_dev, path.stat().st_ino
    foreign = different_payload(path.read_bytes())
    path.write_bytes(foreign)
    assert (path.stat().st_dev, path.stat().st_ino) == original_identity
    with pytest.raises(GpuLockOwnershipError, match="path ownership changed"):
        lock.__exit__()
    assert_closed(fd)
    assert lock._fd is lock._identity is lock._payload is None
    assert path.read_bytes() == foreign
    lock.__exit__()
    assert path.read_bytes() == foreign


@pytest.mark.parametrize("simulate_identity_ABA", [False, True])
def test_foreign_replacement_after_close_preserved(tmp_path, monkeypatch, simulate_identity_ABA):
    path = tmp_path / "gpu.lock"
    lock = GpuFileLock(path).__enter__()
    fd = lock._fd
    assert fd is not None
    foreign = different_payload(path.read_bytes())
    real_close = os.close
    replaced = False

    def close_then_replace(value):
        nonlocal replaced
        real_close(value)
        if value == fd and not replaced:
            replaced = True
            path.unlink()
            path.write_bytes(foreign)

    if simulate_identity_ABA:
        # Deliberately collide identity checks; the exact token-bearing payload
        # must independently reject the replacement. No native ABA claim.
        monkeypatch.setattr(
            GpuFileLock,
            "_same_file",
            staticmethod(lambda info, _identity: stat.S_ISREG(info.st_mode)),
        )
    monkeypatch.setattr(agent.os, "close", close_then_replace)
    with pytest.raises(GpuLockOwnershipError, match="ownership changed"):
        lock.__exit__()
    assert replaced
    assert path.read_bytes() == foreign
    assert lock._fd is None
    lock.__exit__()
    assert path.read_bytes() == foreign


def test_reused_descriptor_is_not_closed(tmp_path):
    path = tmp_path / "gpu.lock"
    lock = GpuFileLock(path).__enter__()
    fd = lock._fd
    assert fd is not None
    original = path.read_bytes()
    other = tmp_path / "unrelated-file"
    other.write_bytes(b"foreign descriptor")
    os.close(fd)
    foreign_fd = os.open(other, os.O_RDWR | getattr(os, "O_BINARY", 0))
    if foreign_fd != fd:
        os.dup2(foreign_fd, fd)
        os.close(foreign_fd)
    try:
        with pytest.raises(GpuLockOwnershipError, match="descriptor ownership changed"):
            lock.__exit__()
        assert path.read_bytes() == original
        assert os.fstat(fd).st_ino == other.stat().st_ino
        lock.__exit__()
        os.fstat(fd)
    finally:
        os.close(fd)


def test_foreign_replacement_after_verification_close_preserved(tmp_path, monkeypatch):
    path, foreign = tmp_path / "gpu.lock", tmp_path / "foreign"
    lock = GpuFileLock(path).__enter__()
    fd = lock._fd
    assert fd is not None
    foreign.write_bytes(b"replacement after verification close")
    real_close = os.close
    closes = 0

    def close_then_replace(value):
        nonlocal closes
        real_close(value)
        closes += 1
        if closes == 2:
            path.unlink()
            foreign.replace(path)

    monkeypatch.setattr(agent.os, "close", close_then_replace)
    with pytest.raises(GpuLockOwnershipError, match="path ownership changed"):
        lock.__exit__()
    assert path.read_bytes() == b"replacement after verification close"
    assert lock._fd is None


def test_unlink_denied_reports_failure_after_own_fd_closed(tmp_path, monkeypatch):
    path = tmp_path / "gpu.lock"
    lock = GpuFileLock(path).__enter__()
    fd = lock._fd
    assert fd is not None
    real_unlink = Path.unlink

    def denied(candidate, *args, **kwargs):
        if candidate == path:
            raise PermissionError("synthetic unlink denial")
        return real_unlink(candidate, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", denied)
        with pytest.raises(GpuLockOwnershipError, match="cleanup failed"):
            lock.__exit__()
    assert_closed(fd)
    assert path.exists()
    assert lock._fd is lock._identity is lock._payload is None
    lock.__exit__()
    assert path.exists()


def test_short_writes_are_completed(tmp_path, monkeypatch):
    path = tmp_path / "gpu.lock"
    lock = GpuFileLock(path)
    real_write = os.write
    writes = []

    def short_write(fd, payload):
        if fd == lock._fd:
            writes.append(len(payload))
            return real_write(fd, payload[:1])
        return real_write(fd, payload)

    monkeypatch.setattr(agent.os, "write", short_write)
    with lock:
        assert path.read_bytes() == lock._payload
        assert len(writes) == len(path.read_bytes()) > 1
        json.loads(path.read_bytes())
    assert not path.exists()


@pytest.mark.parametrize("failure", ["zero_write", "partial_write", "fsync"])
def test_acquisition_failure_closes_own_fd_and_removes_own_prefix(tmp_path, monkeypatch, failure):
    path = tmp_path / "gpu.lock"
    lock = GpuFileLock(path)
    real_write, real_fsync = os.write, os.fsync
    opened = []

    def write(fd, payload):
        opened.append(fd)
        if failure == "zero_write":
            return 0
        if failure == "partial_write":
            if len(opened) == 1:
                return real_write(fd, payload[:13])
            raise OSError("synthetic write failure")
        return real_write(fd, payload)

    def fsync(fd):
        if failure == "fsync":
            raise OSError("synthetic sync failure")
        return real_fsync(fd)

    monkeypatch.setattr(agent.os, "write", write)
    monkeypatch.setattr(agent.os, "fsync", fsync)
    with pytest.raises(OSError):
        lock.__enter__()
    assert opened
    assert_closed(opened[0])
    assert not path.exists()
    assert lock._fd is lock._identity is lock._payload is None
    path.write_bytes(b"later owner")
    lock.__exit__()
    assert path.read_bytes() == b"later owner"


def test_partial_failure_preserves_replacement_and_reused_foreign_fd(tmp_path, monkeypatch):
    path, replacement = tmp_path / "gpu.lock", tmp_path / "replacement"
    replacement.write_bytes(b"foreign lock")
    lock = GpuFileLock(path)
    real_write, real_close = os.write, os.close
    foreign = []

    def replace_during_write(fd, payload):
        real_write(fd, payload[:13])
        real_close(fd)
        path.unlink()
        replacement.replace(path)
        other_fd = os.open(path, os.O_RDWR | getattr(os, "O_BINARY", 0))
        if other_fd != fd:
            os.dup2(other_fd, fd)
            real_close(other_fd)
        foreign.append(fd)
        raise OSError("synthetic interrupted owner")

    monkeypatch.setattr(agent.os, "write", replace_during_write)
    try:
        with pytest.raises(GpuLockOwnershipError, match="descriptor ownership changed"):
            lock.__enter__()
        assert path.read_bytes() == b"foreign lock"
        assert lock._fd is lock._identity is lock._payload is None
        os.fstat(foreign[0])
        lock.__exit__()
        os.fstat(foreign[0])
    finally:
        if foreign:
            real_close(foreign[0])


@pytest.mark.parametrize("bad_field", ["st_dev", "st_ino", "st_file_attributes"])
def test_unavailable_identity_or_reparse_fails_closed(tmp_path, monkeypatch, bad_field):
    path = tmp_path / "gpu.lock"
    lock = GpuFileLock(path)
    real_fstat = os.fstat
    opened = []

    def bad_stat(fd):
        opened.append(fd)
        info = real_fstat(fd)
        fields = dict(
            st_mode=info.st_mode,
            st_dev=info.st_dev,
            st_ino=info.st_ino,
            st_file_attributes=getattr(info, "st_file_attributes", 0),
        )
        fields[bad_field] = 0x400 if bad_field == "st_file_attributes" else 0
        return SimpleNamespace(**fields)

    monkeypatch.setattr(agent.os, "fstat", bad_stat)
    with pytest.raises(OSError, match="identity unavailable"):
        lock.__enter__()
    with pytest.raises(OSError):
        real_fstat(opened[0])
    assert lock._fd is None
    assert path.exists()  # Unknown identity is never used to unlink a pathname.
    lock.__exit__()
    assert path.exists()


def test_leaf_symlink_is_not_followed_or_removed(tmp_path):
    target, path = tmp_path / "foreign", tmp_path / "gpu.lock"
    target.write_bytes(b"foreign lock")
    try:
        path.symlink_to(target)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"native symlink creation unavailable: {type(exc).__name__}")
    loser = GpuFileLock(path)
    with pytest.raises(GpuLockHeldError):
        loser.__enter__()
    loser.__exit__()
    assert path.is_symlink()
    assert target.read_bytes() == b"foreign lock"


def test_parent_symlink_is_rejected(tmp_path):
    target, link = tmp_path / "target", tmp_path / "linked"
    target.mkdir()
    try:
        link.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"native directory link unavailable: {type(exc).__name__}")
    with pytest.raises(ValueError, match="link or reparse point"):
        GpuFileLock(link / "gpu.lock").__enter__()
    assert not (target / "gpu.lock").exists()


@pytest.mark.skipif(os.name != "nt", reason="native Windows junction regression")
def test_native_windows_parent_junction_is_rejected(tmp_path):
    import _winapi

    target, junction = tmp_path / "target", tmp_path / "junction"
    target.mkdir()
    _winapi.CreateJunction(str(target), str(junction))
    try:
        assert junction.lstat().st_file_attributes & 0x400
        with pytest.raises(ValueError, match="link or reparse point"):
            GpuFileLock(junction / "gpu.lock").__enter__()
        assert not (target / "gpu.lock").exists()
    finally:
        junction.rmdir()

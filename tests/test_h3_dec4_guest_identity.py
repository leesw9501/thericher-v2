import hashlib

import pytest

from thericher_v2.ops import h3_dec4_guest_identity as identity


def test_proc_self_parses_kernel_birth_and_raw_nul_argv(monkeypatch):
    monkeypatch.setattr(identity.os, "getpid", lambda: 1)
    argv = ["python", "/app/owned.py", "--execute"]
    cmd = b"python\0/app/owned.py\0--execute\0"
    body = b"1 (invented ) name) R " + b"0 " * 18 + b"8171 0 0\n"
    monkeypatch.setattr(identity, "_read", lambda path, _: body if path.endswith("stat") else cmd)
    answer = identity.read_guest_process()
    assert answer == identity.CapsuleProcess(1, 8171, hashlib.sha256(cmd).hexdigest())
    assert answer.argv_sha256 == identity.linux_argv_sha256(argv)


@pytest.mark.parametrize(
    "changes",
    [
        dict(namespace_pid=True),
        dict(namespace_pid=2),
        dict(start_ticks=0),
        dict(start_ticks=True),
        dict(argv_sha256="!" * 64),
    ],
)
def test_guest_fields_are_exact_and_not_caller_coerced(changes):
    row = dict(namespace_pid=1, start_ticks=15, argv_sha256="a" * 64) | changes
    with pytest.raises(ValueError, match="^h3_guest_identity_unknown$"):
        identity.parse_guest_process(row)

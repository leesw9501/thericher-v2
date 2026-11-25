import hashlib
from pathlib import Path

import pytest

from thericher_v2.ops import h3_dec4_restore_daemon as restore

_ID = b"199eb2d8-0449-41d9-ab7c-88fd7dd81c10"
_PIN = hashlib.sha256(_ID).hexdigest()
_CID = "a" * 64
_VISIT = "b" * 32
_SOURCE = "c" * 64
_RECORD = {
    "identity": {"source": _SOURCE},
    "visits": [{"run": _VISIT, "status": "CLOSED", "create": {"cid": _CID}}],
}


def _driver(replies):
    iterator = iter(replies)
    calls = []

    def invoke(command):
        calls.append(command)
        return next(iterator)

    return invoke, calls


def test_restore_reads_cid_and_labels_including_stopped_containers():
    invoke, calls = _driver([_ID, b"", b"", _ID + b"\r\n"])
    assert restore._probe(invoke, _PIN, _RECORD) is True
    assert calls == [
        ("info", "--format", "{{.ID}}"),
        ("ps", "--all", "--quiet", "--no-trunc", "--filter", f"id={_CID}"),
        (
            "ps",
            "--all",
            "--quiet",
            "--no-trunc",
            "--filter",
            f"label=thericher.single_owner.visit={_VISIT}",
            "--filter",
            f"label=thericher.single_owner.source={_SOURCE}",
        ),
        ("info", "--format", "{{.ID}}"),
    ]


@pytest.mark.parametrize(
    "replies",
    [
        [b"other-local-engine-0123456789"],
        [_ID, _CID.encode()],
        [_ID, b"", b"f" * 64],
        [_ID, b"daemon output was not a container id"],
        [_ID, b"", b"", b"changed-local-engine-0123456789"],
    ],
    ids=(
        "foreign-engine",
        "stopped-cid",
        "different-cid-exact-label",
        "unparseable",
        "engine-drift",
    ),
)
def test_ambiguous_daemon_or_container_withholds_restore(replies):
    invoke, _ = _driver(replies)
    with pytest.raises(ValueError):
        restore._probe(invoke, _PIN, _RECORD)


def test_no_visit_still_needs_a_stable_bound_daemon():
    invoke, calls = _driver([_ID, _ID])
    assert restore._probe(invoke, _PIN, {"visits": []}) is True
    assert len(calls) == 2 and all(call[0] == "info" for call in calls)


def test_daemon_profile_hash_binds_executable_engine_and_config(tmp_path):
    base = restore.Dec4RestoreDaemon("1" * 64, _PIN, tmp_path)
    cases = (
        restore.Dec4RestoreDaemon("2" * 64, _PIN, tmp_path),
        restore.Dec4RestoreDaemon("1" * 64, "2" * 64, tmp_path),
        restore.Dec4RestoreDaemon("1" * 64, _PIN, tmp_path / "other"),
    )
    assert all(case.sha256 != base.sha256 for case in cases)
    with pytest.raises(ValueError):
        restore.Dec4RestoreDaemon("1" * 64, _PIN, Path("relative"))

"""Invented source and receipt tests for the Dec4 forecast launcher boundary."""

import json
import runpy
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/run_h3_dec4_fixed_half.py"
OWNER = SimpleNamespace(**runpy.run_path(str(SCRIPT)))
NATIVE = OWNER.run_fixed_half_owner.__globals__
BIRTH = "win-filetime:134409530000000000"


@pytest.fixture
def box(tmp_path, monkeypatch):
    source = tmp_path / "forecast" / "source"
    data = tmp_path / "data" / "source"
    for name in OWNER._REQUIRED:
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"# invented protected member")
    files = {name: OWNER._sha((source / name).read_bytes()) for name in OWNER._REQUIRED}
    raw = json.dumps(
        dict(schema=OWNER.SOURCE_SCHEMA, run=OWNER.STUDY, tree="a" * 40, files=files)
    ).encode("ascii")
    (source / "SOURCE.json").write_bytes(raw)
    receipt = data.parent / "run" / "OWNER-CLOSED.json"
    receipt.parent.mkdir(parents=True)
    receipt.write_bytes(b'{"synthetic_fixture":true}')
    state = SimpleNamespace(
        now=OWNER.OPENS,
        source=source,
        data=data,
        receipt=receipt,
        pin=OWNER._sha(raw),
        data_digest=OWNER._sha(receipt.read_bytes()),
        current_birth=BIRTH,
    )
    monkeypatch.setitem(NATIVE, "SOURCE", source)
    monkeypatch.setitem(NATIVE, "DATA_SOURCE", data)
    monkeypatch.setitem(NATIVE, "_now", lambda: state.now)
    return state


@pytest.mark.parametrize("problem", ["tampered", "extra", "missing", "wrong_pin"])
def test_exact_forecast_import_tree(box, problem):
    OWNER.verify_source(box.pin)
    path = box.source / OWNER.ENTRY
    if problem == "tampered":
        path.write_bytes(b"# changed")
    elif problem == "extra":
        (box.source / "src/thericher_v2/extra.py").touch()
    elif problem == "missing":
        path.unlink()
    else:
        box.pin = "0" * 64
    with pytest.raises(ValueError, match="dec4_fixed_half_source_"):
        OWNER.verify_source(box.pin)


def test_data_verifier_executes_only_prebound_writer(box, monkeypatch):
    writer = box.data / OWNER.DATA_WRITER
    writer.parent.mkdir(parents=True)
    raw = (
        "from pathlib import Path\n"
        f"DEC3_SOURCE = Path({str(box.data)!r})\n"
        "def verify_source(root, pin, *, dec3):\n"
        "    assert root == DEC3_SOURCE and dec3 is True\n"
        "    assert (root / 'SOURCE.json').read_text() == pin\n"
    ).encode("ascii")
    writer.write_bytes(raw)
    (box.data / "SOURCE.json").write_text(OWNER.DATA_SOURCE_SHA256, encoding="ascii")
    monkeypatch.setitem(NATIVE, "DATA_WRITER_SHA256", OWNER._sha(raw))
    OWNER.verify_data_source()
    writer.write_bytes(b"raise AssertionError('must not execute changed source')")
    with pytest.raises(ValueError, match="^dec4_fixed_half_data_writer$"):
        OWNER.verify_data_source()


def test_sync_closure_requires_exact_receipt_positive_absence_and_stability(box):
    def check(probe, *, digest=box.data_digest):
        return OWNER._closed_sync_data(42, BIRTH, digest, probe=probe)

    def absent(pid):
        assert pid == 42
        return None

    assert check(absent)
    assert not check(lambda pid: BIRTH)
    assert not check(lambda pid: "win-filetime:134409530000000001")
    assert not check(lambda pid: pytest.fail("unbound receipt probed"), digest="a" * 64)

    def denied(pid):
        raise PermissionError

    with pytest.raises(PermissionError):
        check(denied)

    def changed(pid):
        box.receipt.write_bytes(b"changed")
        return None

    assert not check(changed)


@pytest.mark.parametrize("offset, ready", [(-1, True), (60, True), (0, 1)])
def test_blocks_source_access_outside_window_or_without_host(box, monkeypatch, offset, ready):
    def forbidden():
        pytest.fail("unadmitted launch checked runtime")

    monkeypatch.setitem(NATIVE, "_require_runtime", forbidden)
    box.now += timedelta(seconds=offset)
    with pytest.raises(ValueError, match="dec4_fixed_half_launcher_(clock|host)"):
        OWNER.run_fixed_half_owner(box.pin, host_ready=lambda: ready)


@pytest.mark.parametrize("failure", [None, "late", "changed_manifest", "changed_pid"])
def test_calls_named_core_with_sync_closure_and_returns_only_live_digest(box, monkeypatch, failure):
    pid = NATIVE["os"].getpid()
    data_pid = pid + 1
    events = []
    monkeypatch.setitem(NATIVE, "_require_runtime", lambda: events.append("runtime"))
    monkeypatch.setitem(NATIVE, "verify_data_source", lambda: events.append("data"))

    def probe(requested):
        if requested == data_pid:
            return None
        assert requested == pid
        return box.current_birth

    def forecast(*, forecast_source_sha256, clock, owner_ready, data_owner_closed):
        events.append("forecast")
        assert forecast_source_sha256 == box.pin
        assert clock() == OWNER.OPENS
        assert owner_ready()
        assert data_owner_closed(data_pid, BIRTH, box.data_digest)
        if failure == "late":
            box.now = OWNER.HARD_STOP
        elif failure == "changed_manifest":
            (box.source / "SOURCE.json").write_bytes(b"changed")
        elif failure == "changed_pid":
            box.current_birth = None
        return "c" * 64

    monkeypatch.setitem(NATIVE, "_bind_core", lambda: (forecast, probe))
    if failure:
        with pytest.raises(ValueError, match="dec4_fixed_half_launcher_(clock|result)"):
            OWNER.run_fixed_half_owner(box.pin, host_ready=lambda: True)
    else:
        assert OWNER.run_fixed_half_owner(box.pin, host_ready=lambda: True) == "c" * 64
    assert events == ["runtime", "data", "forecast"]
    assert not (box.source.parent / "run").exists()


def test_cli_has_no_unattested_activation():
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(SCRIPT), run_name="__main__")
    assert exc.value.code == 20

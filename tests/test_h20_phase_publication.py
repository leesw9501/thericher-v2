import json
from datetime import timedelta
from hashlib import sha256

import pytest

from thericher_v2.ops import h20_phase_host as host
from thericher_v2.ops import h20_phase_publication as publication
from thericher_v2.ops.h20_exact_phase_outcomes import _result
from thericher_v2.ops.h20_phase_transport import _PHASES

_PUBLIC_READER = b"""
def need(ok):
    if not ok:
        raise ValueError('synthetic native evidence mismatch')

def same(record, path):
    need(record == pointer(path))

def validate(run, source_pin, binding, coordinator_pin):
    result = read(run / 'RESULT.json')
    before = pointer(run / 'RESULT.json')
    need(result['source_sha256'] == source_pin)
    need(result['H20_source'] == binding['installed_host'])
    same(result['H20_source'], Path(binding['installed_host']['path']))
    need(result['input_ref'] == binding['input_ref'])
    same(result['closure'], run / 'CLOSED.json')
    closed = read(run / 'CLOSED.json')
    need(closed['admissions'] == result['admissions'])
    need([a['phase'] for a in closed['admissions']] == PHASES)
    for row in closed['admissions']:
        need(row['actual_caller']['source_sha256'] == coordinator_pin)
        same(row['verdict'], run / ('CAPABILITY-' + row['phase'] + '.json'))
    value = result['result']
"""


def _pointer(path):
    raw = path.read_bytes()
    return dict(path=str(path), bytes=len(raw), sha256=sha256(raw).hexdigest())


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    public = tmp_path / "public.py"
    public.write_bytes(_PUBLIC_READER)
    monkeypatch.setattr(host, "_PUBLIC", public)
    monkeypatch.setattr(host, "_PUBLIC_PIN", sha256(_PUBLIC_READER).hexdigest())
    monkeypatch.setattr(host, "_READER", public)
    monkeypatch.setattr(host, "_load", lambda _: {"REASONS": {"OK"}, "STAGES": {"COMPLETE"}})
    # Transport may close after LAST_START; publication has the same hard stop.
    monkeypatch.setattr(publication, "_utc_now", lambda: host.LAST_START)
    run = tmp_path / "run"
    run.mkdir()
    protected = tmp_path / "protected"
    protected.mkdir()
    coordinator_pin = "b" * 64
    admissions = []
    for phase in _PHASES:
        receipt = run / f"CAPABILITY-{phase}.json"
        receipt.write_bytes(b'{"status":"NO_CURRENT_PRIVATE_CUSTODY_WRITER_OBSERVED"}')
        admissions.append(
            dict(
                phase=phase,
                verdict=_pointer(receipt),
                actual_caller={
                    "source_sha256": coordinator_pin,
                    "origin": "actual_source_caller_not_OS_scheduler_proof",
                    "pid": 20,
                    "created_filetime": 42,
                    "argv_sha256": "c" * 64,
                },
            )
        )
    result = _result("OK", "COMPLETE")
    result["entry"]["plan"] = "LINKED"
    result["exit"]["plan"] = "NO_LINKED_PLAN"
    closure = dict(
        status="PASS",
        CID_absent=True,
        admissions=admissions,
        Jobs=[dict(exit=0, active=0, closed=True)],
    )
    binding = {
        key: _pointer(public)
        for key in ("reader_source", "installed_host", "release", "plan", "contract")
    }
    binding.update(input_ref="invented-input", policy_ref="invented-policy")
    return dict(
        run=run,
        protected_digest=protected / "RESULT.sha256",
        source_pin="a" * 64,
        binding=binding,
        coordinator_pin=coordinator_pin,
        completed=(result, closure),
    )


def _read(inputs):
    return publication.read_published_h20_phase_result(
        **{key: value for key, value in inputs.items() if key != "completed"}
    )


def test_publish_binds_both_files_and_reads_after_window(inputs, monkeypatch):
    projection = publication.publish_h20_phase_result(**inputs)
    result_path = inputs["run"] / "RESULT.json"
    closed_path = inputs["run"] / "CLOSED.json"
    envelope = json.loads(result_path.read_bytes())
    assert envelope["closure"] == _pointer(closed_path)
    assert json.loads(closed_path.read_bytes()) == inputs["completed"][1]
    assert (
        inputs["protected_digest"].read_text(encoding="ascii")
        == _pointer(result_path)["sha256"] + "\n"
    )
    assert projection["status"] == "VALIDATED_CURRENT_RETAINED_PHASE_STATE"
    assert projection["OS_scheduler_origin"] == "NOT_CRYPTOGRAPHICALLY_PROVEN"
    assert projection["net_PnL"] == "UNKNOWN"
    monkeypatch.setattr(publication, "_utc_now", lambda: host.HARD_STOP)
    assert _read(inputs) == projection


@pytest.mark.parametrize("fault", ["early", "late", "in_run", "unclosed", "unqualified_dto"])
def test_reject_before_writing(inputs, monkeypatch, fault):
    if fault in {"early", "late"}:
        now = host.OPENS - timedelta(microseconds=1) if fault == "early" else host.HARD_STOP
        monkeypatch.setattr(publication, "_utc_now", lambda: now)
    elif fault == "in_run":
        inputs["protected_digest"] = inputs["run"] / "digest"
    elif fault == "unclosed":
        inputs["completed"][1]["Jobs"][0]["active"] = 1
    else:
        inputs["completed"][0]["raw"] = "not a public field"
    with pytest.raises(ValueError):
        publication.publish_h20_phase_result(**inputs)
    assert not inputs["protected_digest"].exists()
    assert not list(inputs["run"].glob("CLOSED*"))
    assert not list(inputs["run"].glob("RESULT*"))


@pytest.mark.parametrize("name", ["CLOSED.json", "RESULT.json", "RESULT.sha256"])
def test_never_replaces_existing_output(inputs, name):
    paths = [
        inputs["run"] / "CLOSED.json",
        inputs["run"] / "RESULT.json",
        inputs["protected_digest"],
    ]
    existing = next(path for path in paths if path.name == name)
    existing.write_bytes(b"already claimed")
    with pytest.raises(ValueError):
        publication.publish_h20_phase_result(**inputs)
    assert existing.read_bytes() == b"already claimed"
    assert [path for path in paths if path.exists()] == [existing]


@pytest.mark.parametrize("fault", ["unbound", "expired", "changed_closed", "changed_result"])
def test_withholds_digest_on_failed_readback(inputs, monkeypatch, fault):
    read = publication.read_h20_phase_envelope

    def readback(*args, **kwargs):
        result = read(*args, **kwargs)
        if fault == "expired":
            monkeypatch.setattr(publication, "_utc_now", lambda: host.HARD_STOP)
        elif fault.startswith("changed_"):
            name = fault.removeprefix("changed_").upper() + ".json"
            path = inputs["run"] / name
            path.write_bytes(path.read_bytes() + b" ")
        return result

    if fault == "unbound":
        inputs["coordinator_pin"] = "d" * 64
    monkeypatch.setattr(publication, "read_h20_phase_envelope", readback)
    with pytest.raises(ValueError):
        publication.publish_h20_phase_result(**inputs)
    assert not inputs["protected_digest"].exists()
    with pytest.raises(FileNotFoundError):
        _read(inputs)


@pytest.mark.parametrize("name", ["CLOSED.json", "RESULT.json", "RESULT.sha256"])
def test_subsequent_read_never_repins_changed_bytes(inputs, name):
    publication.publish_h20_phase_result(**inputs)
    path = inputs["protected_digest"] if name.endswith("sha256") else inputs["run"] / name
    raw = path.read_bytes()
    path.write_bytes(raw + b" ")
    with pytest.raises(ValueError):
        _read(inputs)


def test_commit_race_does_not_replace_digest(inputs, monkeypatch):
    link = publication.os.link

    def competing_link(pending, destination):
        destination.write_bytes(b"competing writer")
        link(pending, destination)

    monkeypatch.setattr(publication.os, "link", competing_link)
    with pytest.raises(FileExistsError):
        publication.publish_h20_phase_result(**inputs)
    digest = inputs["protected_digest"]
    assert digest.read_bytes() == b"competing writer"
    assert list(digest.parent.iterdir()) == [digest]

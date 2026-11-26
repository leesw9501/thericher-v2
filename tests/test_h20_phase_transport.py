import json
from datetime import timedelta
from hashlib import sha256
from types import SimpleNamespace

import pytest

from thericher_v2.ops import h20_phase_transport as transport


def test_retained_sources_load_without_launch():
    if not transport._ROOT.is_dir():
        pytest.skip("pinned native H20 transport not retained on this host")
    configure, bounded, share = transport._native_sources()
    assert configure.__name__ == "configure"
    assert bounded.__mro__[1].__name__ == "Transport"
    assert share.__name__ == "share_deadline"


def test_deadline_no_early_or_late_start_and_cleanup_has_own_reserve(monkeypatch):
    now = transport.LAST_START - timedelta(seconds=1)
    elapsed = 100.0
    monkeypatch.setattr(transport, "_utc_now", lambda: now)
    monkeypatch.setattr(transport.time, "monotonic", lambda: elapsed)
    bound = transport._Dec1Deadline()
    elapsed += 149.5
    assert bound.remaining() == 0.5
    elapsed += 1
    with pytest.raises(TimeoutError):
        bound.remaining()
    assert bound.remaining(cleanup=True) == 29.5
    # A forward wall-clock correction cannot let even cleanup keep running.
    now = transport.HARD_STOP
    with pytest.raises(TimeoutError):
        bound.remaining(cleanup=True)
    for outside_window in (transport.OPENS - timedelta(seconds=1), transport.LAST_START):
        now = outside_window
        with pytest.raises(ValueError, match="H20_PHASE_HOST_UNQUALIFIED"):
            transport._Dec1Deadline()


@pytest.mark.parametrize(
    "fault", [None, "denied", "wrong_caller", "wrong_phase", "cid", "job", "exit_unlinked"]
)
def test_transport_returns_only_on_complete_native_chain(monkeypatch, tmp_path, fault):
    monkeypatch.setattr(transport, "_utc_now", lambda: transport.OPENS)
    entry = tmp_path / "entry.py"
    entry.write_bytes(b"pinned invented source")
    pin = sha256(entry.read_bytes()).hexdigest()
    output = tmp_path / "out"
    output.mkdir()
    starts = []
    namespace = dict(SOURCE={"image": "image"}, JOB=object(), PHASES=[])

    def census(phase, **kwargs):
        path = output / ("CAPABILITY-" + phase + ".json")
        path.write_text(
            json.dumps(
                {
                    "status": "UNKNOWN"
                    if fault == "denied"
                    else "NO_CURRENT_PRIVATE_CUSTODY_WRITER_OBSERVED"
                }
            ),
            encoding="ascii",
        )
        identity = dict(
            source_sha256=pin,
            origin="actual_source_caller_not_OS_scheduler_proof",
            pid=1,
            created_filetime=3 if fault == "wrong_caller" and phase == "before_read" else 2,
            argv_sha256="d" * 64,
        )
        namespace["PHASES"].append({"exact_own": identity})
        return True

    class Native:
        def __init__(self, job, env, fresh, deadline):
            assert job is namespace["JOB"]
            self.fresh = fresh
            self.cid_absent = fault != "cid"
            self.jobs = [dict(exit=0, active=0, closed=fault != "job")]

        def invoke(self, *_):
            starts.append(True)
            phases = transport._PHASES if fault != "wrong_phase" else transport._PHASES[::-1]
            for phase in phases:
                assert self.fresh(phase=phase, cid=None, mounts=[], children=[]) is True
            return {"invented": True}

    def configure(binding, out, entry_file):
        assert fault != "exit_unlinked"
        assert out == output and entry_file == entry
        return SimpleNamespace(namespace=namespace, fresh=census)

    monkeypatch.setattr(transport, "_native_sources", lambda: (configure, Native, lambda *_: None))
    monkeypatch.setattr(transport, "bind_h20_web_census", lambda *_: None)
    monkeypatch.setattr(
        transport,
        "prove_h20_exit_read_boundary",
        lambda *, owner_closed: owner_closed(transport.prove_h20_exit_read_boundary, 123),
    )
    monkeypatch.setattr(
        transport,
        "prove_h20_exit_outer_owner_closed",
        lambda _task, pid, *, timeout: pid == 123 and 0 < timeout <= 8 and fault != "exit_unlinked",
    )
    monkeypatch.setattr(
        transport,
        "invoke_h20_phase_window",
        lambda **kw: kw["transport"]() if kw["admission_ready"]() else pytest.fail("source"),
    )

    def run():
        return transport.run_h20_phase_transport(
            binding=dict(mounts=[], sanitized_environment={}),
            out=output,
            entry_file=entry,
            entry_sha256=pin,
            guest_sha256="guest",
            image="image",
        )

    if fault is not None:
        with pytest.raises(ValueError, match="H20_PHASE_HOST_UNQUALIFIED"):
            run()
    else:
        result, closed = run()
        assert result == {"invented": True}
        assert closed["status"] == "PASS"
        assert [r["phase"] for r in closed["admissions"]] == list(transport._PHASES)
    assert starts == ([] if fault == "exit_unlinked" else [True])

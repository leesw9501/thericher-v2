import os
from datetime import datetime

import pytest

from thericher_v2.ops.paper_scheduled_native import run_native_scheduled_preflight

PIN = "1" * 64
RELEASE = "2" * 64
START = "2030-01-02T14:31:00+00:00"
END = "2030-01-02T14:35:00+00:00"
HARD = "2030-01-02T14:37:00+00:00"
ACTION_SHA = "54efb9b60585ad9ae38e4af5611102300237aa1b6f166c0ed81b8e82b12eb55b"


class Source:
    ROUND = "invented-native-slot"
    SLOTS = {"entry": dict(name="test-paper-entry", start_UTC=START, end_UTC=END, hard_UTC=HARD)}

    def __init__(self, root):
        self.ROOT = root
        self.calls = []
        self.release_allowed = True

    def action(self, pin, release_pin, phase):
        assert (pin, release_pin, phase) == (PIN, RELEASE, "entry")
        return "invented exact action"

    def check(self, pin):
        self.calls.append("source")
        assert pin == PIN
        return {"verified": True}

    def release(self, value, pin, digest):
        self.calls.append("release")
        assert (value, pin, digest) == ({"verified": True}, PIN, RELEASE)
        return dict(
            source=PIN, allow_execute=self.release_allowed, actual_financial_admission=False
        )

    def window(self, phase, at):
        self.calls.append("window")
        assert (phase, at) == ("entry", datetime.fromisoformat(START))
        return tuple(datetime.fromisoformat(d) for d in (START, END))


class Probe:
    def __init__(self, source):
        self.calls = source.calls
        self.expected = dict(
            dispatcher_source=PIN,
            dispatcher_release=RELEASE,
            dispatcher_root=str(source.ROOT),
            task_name="test-paper-entry",
            task_action_sha256=ACTION_SHA,
            round_id="invented-native-slot",
        )
        self.proof = self.expected | dict(
            schema="paper-stock-ingress-owner-v1",
            status="PASS_STOCK_INGRESS_SCHEDULED_OWNER",
            origin="ACTUAL_STOCK_INGRESS_TASK_SOURCE_ABI",
            no_old_model_self_rows=True,
            pid=os.getpid(),
            start_ticks="1234",
            argv_sha256="6" * 64,
        )

    def prove(self):
        self.calls.append("owner")
        return self.proof


@pytest.fixture
def harness(tmp_path):
    source = Source(tmp_path)
    probe = Probe(source)

    def make_owner(pin, phase, release_pin):
        assert (pin, phase, release_pin) == (PIN, "entry", RELEASE)
        return probe

    def run():
        result = run_native_scheduled_preflight(
            tmp_path,
            source=source,
            pin=PIN,
            release_pin=RELEASE,
            phase="entry",
            clock=lambda: datetime.fromisoformat(START),
            make_owner=make_owner,
        )
        source.calls.append("before-native-attempt")
        return result

    return source, probe, run


def test_native_launch_returns_same_owner_and_stops_before_runtime(harness):
    source, probe, run = harness
    result = run()
    assert result.owner is probe
    assert source.calls == ["source", "release", "window", "owner", "before-native-attempt"]
    assert result.plan.hard_stop == datetime.fromisoformat(HARD)
    assert result.release["actual_financial_admission"] is False
    assert len(list(source.ROOT.glob("*/CLAIM.json"))) == 1


@pytest.mark.parametrize(
    ("field", "bad"),
    [
        ("pid", -1),
        ("start_ticks", "0"),
        ("argv_sha256", "wrong"),
        ("task_name", "another-task"),
        ("task_action_sha256", "f" * 64),
        ("origin", "fixture-only"),
    ],
)
def test_native_owner_mismatch_does_not_consume_slot(harness, field, bad):
    source, probe, run = harness
    original = probe.proof[field]
    probe.proof[field] = bad
    with pytest.raises(ValueError, match="owner proof mismatch"):
        run()
    assert "before-native-attempt" not in source.calls
    assert not list(source.ROOT.glob("*/CLAIM.json"))
    probe.proof[field] = original
    assert run().owner is probe


def test_mismatched_expectations_do_not_call_native_probe(harness):
    source, probe, run = harness
    probe.expected["task_action_sha256"] = "f" * 64
    with pytest.raises(ValueError, match="owner expectation mismatch"):
        run()
    assert "owner" not in source.calls


def test_withheld_release_never_probes_owner(harness):
    source, _probe, run = harness
    source.release_allowed = False
    with pytest.raises(ValueError, match="release withheld"):
        run()
    assert source.calls == ["source", "release"]

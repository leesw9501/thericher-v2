import hashlib
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from thericher_v2.execution import paper_peer_visit as pv
from thericher_v2.ops.h3_dec4_observer_lease import Dec4ObserverLease, ObserverSnapshot
from thericher_v2.ops.h3_dec4_observer_plan import (
    OBSERVER_API7_SHA256,
    OBSERVER_TASK_PATH,
    OBSERVER_XML_SHA256,
    Dec4ObserverPlan,
)

_OPEN = datetime(2026, 12, 4, 14, 31, tzinfo=UTC)
_ORIGINAL = ObserverSnapshot(
    OBSERVER_TASK_PATH, True, True, 0, OBSERVER_XML_SHA256, OBSERVER_API7_SHA256, "b" * 64, 19
)
_OFF = replace(_ORIGINAL, enabled=False, xml_sha256="c" * 64)
_BANK = dict(engine="npipe:////./pipe/dockerdesktoplinuxengine", volume="invented-bank")


class _Transport:
    def __init__(self):
        self.current = _ORIGINAL
        self.failure = False
        self.attempts = []
        self.sample_hook = None
        self.next_snapshot = None

    def sample(self, *, enabled):
        if self.current.enabled is not enabled:
            raise ValueError("transport_enabled_drift")
        if self.sample_hook:
            self.sample_hook()
        return self.current

    def switch(self, before, *, enabled, attempt, attempt_sha256):
        assert before == self.current
        raw = attempt.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == attempt_sha256
        assert attempt.name == ("RESTORE_STARTED.json" if enabled else "STARTED.json")
        self.attempts.append((enabled, pv._decode(raw)))
        self.current = self.next_snapshot or (_ORIGINAL if enabled else _OFF)
        if self.failure:
            raise OSError("invented interrupted transport")
        return self.current


@pytest.fixture
def held(tmp_path):
    plan = Dec4ObserverPlan("entry", r"D:\invented\dispatcher", "1" * 64, "2" * 64)
    output = tmp_path / "observed"
    output.mkdir()
    key = pv.bank_key(_BANK)
    identity = dict(
        source="3" * 64,
        release="4" * 64,
        group="3" * 64,
        member="stock-ingress",
        run="5" * 32,
        argv_sha256="6" * 64,
        bank=key,
    )
    leg = pv.BankLeg(
        tmp_path, bank=_BANK, identity=identity, process_probe=lambda _: "win-filetime:7"
    )
    transport = _Transport()
    lease = Dec4ObserverLease(plan, output, transport)
    ready = SimpleNamespace(
        plan=SimpleNamespace(phase="entry", source_sha256="3" * 64, release_sha256="4" * 64),
        source={
            "restore_native": {
                "entry": {
                    "pins": dict(
                        observer_plan_sha256=plan.sha256,
                        observer_restore_daemon_sha256="5" * 64,
                        observer_restore_writer_guard_sha256="6" * 64,
                    )
                },
                "exit": {},
            }
        },
    )
    return leg, lease, transport, ready


def _begin(held):
    leg, lease, _transport, ready = held
    lease.begin(leg, ready, clock=lambda: _OPEN)


def _restore(held, *, original_still_running=False, native_closed=lambda _: True, identity=None):
    leg, lease, _transport, _ready = held
    return lease._restore_closed(
        leg.root.parent,
        _BANK,
        identity or leg.identity,
        native_closed,
        lambda: _OPEN + timedelta(minutes=10),
        lambda _: "win-filetime:7" if original_still_running else None,
    )


def test_original_disable_record_then_exact_normal_restore(held):
    leg, lease, transport, _ready = held
    with leg:
        assert lease.renew_if_started(leg) is True
        assert transport.attempts == []
        _begin(held)
        [(enabled, start)] = transport.attempts
        assert enabled is False and start["identity"] == leg.identity
        assert start["owner"] == leg.record["owner"]
        assert lease.renew_if_started(leg) is True
        leg.close()
    with pytest.raises(ValueError, match="restore_owner_not_closed"):
        _restore(held, original_still_running=True)
    with pytest.raises(ValueError, match="restore_native_closure_unknown"):
        _restore(held, native_closed=lambda _: False)
    _restore(held)
    assert [enabled for enabled, _ in transport.attempts] == [False, True]
    restored = pv._decode((lease.root / "RESTORED.json").read_bytes())
    assert restored["observed"]["xml_sha256"] == OBSERVER_XML_SHA256
    with pytest.raises(ValueError, match="restore_already_attempted"):
        _restore(held)


def test_interrupted_disable_never_restarts_or_claims_restoration(held):
    leg, lease, transport, ready = held
    with leg:
        transport.failure = True
        with pytest.raises(OSError):
            _begin(held)
        assert lease.inspect_interrupted_disable() == "disabled_shape_observed"
        with pytest.raises(ValueError, match="disable_unknown"):
            lease.renew_if_started(leg)
        fresh = Dec4ObserverLease(lease.plan, lease.root, transport)
        with pytest.raises(ValueError, match="disable_already_attempted"):
            fresh.begin(leg, ready, clock=lambda: _OPEN)
        leg.close()
    with pytest.raises(FileNotFoundError):
        _restore(held)
    assert len(transport.attempts) == 1


@pytest.mark.parametrize("change", [{"last_run": 20}, {"instances": 1}, {"shape_sha256": "d" * 64}])
def test_outstanding_observer_or_definition_drift_never_admits(held, change):
    leg, lease, transport, _ready = held
    with leg:
        transport.next_snapshot = replace(_OFF, **change)
        with pytest.raises(ValueError, match="observer_"):
            _begin(held)
        assert not (lease.root / "DISABLED.json").exists()
        assert lease.inspect_interrupted_disable() == "unknown"
        leg.close()


def test_modified_disabled_receipt_and_wrong_original_cannot_restore(held):
    leg, lease, transport, _ready = held
    with leg:
        _begin(held)
        transport.current = replace(_OFF, last_run=80)
        with pytest.raises(ValueError, match="disabled_readback_changed"):
            lease.renew_if_started(leg)
        transport.current = _OFF
        leg.close()
    with pytest.raises(ValueError, match="restore_binding"):
        _restore(held, identity=leg.identity | {"run": "e" * 32})
    disabled = lease.root / "DISABLED.json"
    wrong = pv._decode(disabled.read_bytes()) | {"start_sha256": "f" * 64}
    disabled.write_bytes(pv.encode(wrong))
    with pytest.raises(ValueError, match="restore_binding"):
        _restore(held)
    assert len(transport.attempts) == 1


def test_interrupted_restore_holds_exact_attempt_even_if_reenable_landed(held):
    leg, lease, transport, _ready = held
    with leg:
        _begin(held)
        leg.close()
    transport.failure = True
    with pytest.raises(OSError):
        _restore(held)
    assert transport.current.enabled
    assert not (lease.root / "RESTORED.json").exists()
    with pytest.raises(ValueError, match="restore_already_attempted"):
        _restore(held)
    assert len(transport.attempts) == 2

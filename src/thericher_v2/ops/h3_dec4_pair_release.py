"""Shared immutable release and phase-local restore pins for the Dec4/9 pair."""

from dataclasses import dataclass
from hashlib import sha256

from thericher_v2.execution import paper_peer_visit as pv

_PHASES = ("entry", "exit")
_PINS = {
    "observer_plan_sha256",
    "observer_restore_daemon_sha256",
    "observer_restore_writer_guard_sha256",
}


def _need(ok):
    pv._need(ok, "h3_dec4_pair_release")


def phase_restore_pins(source, phase):
    _need(phase in _PHASES and type(source) is dict)
    rows = source.get("restore_native")
    _need(type(rows) is dict and rows.keys() == set(_PHASES))
    row = rows.get(phase)
    _need(type(row) is dict)
    pins = row.get("pins")
    _need(type(pins) is dict and pins.keys() == _PINS and all(map(pv._hash, pins.values())))
    return pins


def read_pair_release(source_root, phase, source_pin, release_pin):
    """Authenticate both static grants and select one; no sibling runtime check."""
    _need(phase in _PHASES and pv._hash(source_pin) and pv._hash(release_pin))
    raw, _ = pv._read(source_root.parent / "RELEASE.json")
    _need(sha256(raw).hexdigest() == release_pin)
    value = pv._decode(raw)
    _need(
        type(value) is dict
        and value.keys() == {"schema", "source", "phases"}
        and value["schema"] == "h3-dec4-protected-pair-release-v1"
        and value["source"] == source_pin
        and type(value["phases"]) is dict
        and value["phases"].keys() == set(_PHASES)
    )
    for name, grant in value["phases"].items():
        _need(
            type(grant) is dict
            and grant.keys() == {"phase", "allow_execute", "actual_financial_admission"}
            and grant["phase"] == name
            and grant["allow_execute"] is True
            and grant["actual_financial_admission"] is False
        )
    return {"source": source_pin, **value["phases"][phase]}


@dataclass(frozen=True, slots=True, repr=False)
class Dec4PairSource:
    """Keep the launcher's source verifier while fixing the release reader."""

    original: object
    phase: str

    @property
    def ROOT(self):
        return self.original.ROOT

    @property
    def ROUND(self):
        return self.original.ROUND

    @property
    def SLOTS(self):
        return self.original.SLOTS

    def check(self, pin):
        return self.original.check(pin)

    def release(self, value, pin, digest):
        _need(value.get("synthetic_only", False) is False)
        phase_restore_pins(value, self.phase)
        return read_pair_release(self.ROOT, self.phase, pin, digest)

    def action(self, pin, release_pin, phase):
        _need(phase == self.phase)
        return self.original.action(pin, release_pin, phase)

    def window(self, phase, at):
        _need(phase == self.phase)
        return self.original.window(phase, at)

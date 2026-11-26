"""Materialize the native restore binding from the protected Dec4 phase source."""

from dataclasses import dataclass
from datetime import timedelta
from hashlib import sha256
from pathlib import Path
from subprocess import list2cmdline

from thericher_v2.execution import paper_peer_visit as pv
from thericher_v2.ops.h3_dec4_bank_visit import _TIMES, ROUND, TASKS
from thericher_v2.ops.h3_dec4_monitor_mount import Dec4MonitorMount
from thericher_v2.ops.h3_dec4_observer_lease import Dec4ObserverLease
from thericher_v2.ops.h3_dec4_observer_plan import Dec4ObserverPlan
from thericher_v2.ops.h3_dec4_observer_transport import Dec4NativeObserverTransport
from thericher_v2.ops.h3_dec4_pair_release import phase_restore_pins, read_pair_release
from thericher_v2.ops.h3_dec4_restore_child import Dec4RestoreChildBinding
from thericher_v2.ops.h3_dec4_restore_daemon import Dec4RestoreDaemon
from thericher_v2.ops.h3_dec4_restore_writer_guard import Dec4RestoreWriterGuard
from thericher_v2.ops.h3_dec4_writer_census import _PWSH, Dec4CensusProfile, Dec4WriterCensus
from thericher_v2.ops.paper_scheduled_preflight import ScheduledPaperPlan

_ROOT = Path("D:/thericher-v2/model-artifacts/execution")


def _need(ok):
    pv._need(ok, "h3_restore_native_binding")


def _path(value):
    _need(type(value) is str)
    path = Path(value)
    _need(
        path.is_absolute()
        and path != _ROOT
        and path.is_relative_to(_ROOT)
        and ".." not in path.parts
    )
    pv.ordinary(path)
    return path


def _keys(value, keys):
    _need(type(value) is dict and value.keys() == set(keys.split()))


@dataclass(frozen=True, slots=True, repr=False)
class _PhaseSource:
    ROOT: Path
    phase: str
    pin: str
    release_pin: str
    ROUND = ROUND

    @property
    def SLOTS(self):
        start, end, hard = _TIMES[self.phase]
        return {
            self.phase: dict(
                name=TASKS[self.phase],
                start_UTC=start.isoformat(),
                end_UTC=end.isoformat(),
                hard_UTC=hard.isoformat(),
            )
        }

    def check(self, pin):
        _need(pin == self.pin)
        raw, _ = pv._read(self.ROOT / "SOURCE.json")
        _need(pv._hash(pin) and sha256(raw).hexdigest() == pin)
        return pv._decode(raw)

    def release(self, value, pin, digest):
        _need(value.get("synthetic_only", False) is False)
        _need(pin == self.pin and digest == self.release_pin and pv._hash(digest))
        return read_pair_release(self.ROOT, self.phase, pin, digest)


def build_dec4_restore_binding(root, phase, source_sha256, release_sha256):
    """The source/release hashes come from the installed phase, never a model output."""
    try:
        return _build(root, phase, source_sha256, release_sha256)
    except Exception:
        raise pv.Denied("h3_restore_native_binding") from None


def _build(root, phase, source_sha256, release_sha256):
    _need(type(root) is type(_ROOT) and phase in _TIMES and _path(str(root)) == root)
    source = _PhaseSource(root, phase, source_sha256, release_sha256)
    value = source.check(source_sha256)
    source.release(value, source_sha256, release_sha256)
    row = value["restore_native"][phase]
    _keys(row, "launcher evidence_root observer daemon writers pins")
    pins = phase_restore_pins(value, phase)
    obs, d, w = row["observer"], row["daemon"], row["writers"]
    _keys(obs, "package_root bridge_sha256 core_sha256 pwsh pwsh_sha256")
    _keys(d, "docker_sha256 daemon_id_sha256 empty_docker_config")
    _keys(
        w,
        "claims_path claims_sha256 sensitive protected financial_entries "
        "monitor_image retirement_helper retirement_helper_sha256 retirement_roster "
        "retirement_roster_sha256",
    )
    bank = value["original_owner"]["bank"]
    key = pv.bank_key(bank)
    gate = _path(value["original_gate_root"])
    evidence = _path(row["evidence_root"])
    obs_plan = Dec4ObserverPlan(
        phase, str(_path(obs["package_root"])), obs["bridge_sha256"], obs["core_sha256"]
    )
    _need(Path(obs["pwsh"]) == _PWSH)
    lease = Dec4ObserverLease(
        obs_plan,
        Path(obs_plan.output_root),
        Dec4NativeObserverTransport(
            obs_plan, Path(obs["pwsh"]), obs["pwsh_sha256"], bounded_normal_restore=True
        ),
    )
    daemon = Dec4RestoreDaemon(
        d["docker_sha256"], d["daemon_id_sha256"], _path(d["empty_docker_config"])
    )
    _need(all(type(w[name]) is list for name in ("sensitive", "protected", "financial_entries")))
    monitor = (
        None if w["monitor_image"] is None else Dec4MonitorMount(w["monitor_image"], bank["volume"])
    )
    census = Dec4WriterCensus(
        Dec4CensusProfile(
            _path(w["claims_path"]),
            w["claims_sha256"],
            obs["pwsh_sha256"],
            d["docker_sha256"],
            daemon.empty_docker_config,
            tuple(w["sensitive"]),
            tuple(w["protected"]),
            tuple(w["financial_entries"]),
            monitor,
        )
    )
    guard = Dec4RestoreWriterGuard(
        census,
        _path(w["retirement_helper"]),
        w["retirement_helper_sha256"],
        _path(w["retirement_roster"]),
        w["retirement_roster_sha256"],
        gate,
        key,
        bank["volume"],
    )
    _need(
        pins["observer_plan_sha256"] == obs_plan.sha256
        and pins["observer_restore_daemon_sha256"] == daemon.sha256
        and pins["observer_restore_writer_guard_sha256"] == guard.sha256
        and value["single_bank_writer_gate"] == dict(gate_root=str(gate), bank_key=key)
    )
    launcher = _path(row["launcher"])
    _need(launcher.is_relative_to(root) and launcher.relative_to(root).as_posix() in value["files"])
    exe = Path(value["restore_bootstrap"]["executable"])
    _need(exe.is_absolute() and exe.name.casefold() == "pythonw.exe")
    args = [
        "-I",
        "-S",
        "-B",
        str(launcher),
        "--phase",
        phase,
        "--source-sha256",
        source_sha256,
        "--release-sha256",
        release_sha256,
    ]
    action = pv.digest(
        dict(executable=str(exe), arguments=list2cmdline(args), working_directory=str(root))
    )
    plan = ScheduledPaperPlan(
        ROUND, phase, TASKS[phase], action, source_sha256, release_sha256, *_TIMES[phase]
    )

    def hold(record):
        return guard.hold(record, deadline=plan.hard_stop + timedelta(seconds=30))

    return Dec4RestoreChildBinding(
        source, plan, evidence, lease, daemon, hold, guard.retirement_ready
    )

"""Credential-free Dec9 bootstrap source and native callable binding checks."""

import importlib.util
import json
import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

from thericher_v2.execution import paper_peer_visit
from thericher_v2.execution.kis_market_data import KisPaperMarketDataConfig
from thericher_v2.execution.kis_paper_data_capture import CaptureReadiness
from thericher_v2.ops.h3_dec9_fixed_half_target import ENTRY_OPEN, Dec9TargetPins

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts/run_h3_dec9_target_owner.py"
SPEC = importlib.util.spec_from_file_location("dec9_bootstrap_test", SCRIPT)
BOOT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BOOT)
OWNER = "src/thericher_v2/ops/h3_dec9_target_owner.py"


def _freeze(root, members, **override):
    for name, data in members.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    manifest = dict(
        schema=BOOT.SOURCE_SCHEMA,
        run=BOOT.RUN_NAME,
        tree="a" * 40,
        files={key: BOOT._sha(raw) for key, raw in members.items()},
    )
    manifest.update(override)
    raw = json.dumps(manifest).encode()
    (root / "SOURCE.json").write_bytes(raw)
    return BOOT._sha(raw)


@pytest.fixture
def frozen(tmp_path, monkeypatch):
    root = tmp_path / "source"
    monkeypatch.setattr(BOOT, "SOURCE", root)
    members = dict.fromkeys(BOOT._REQUIRED, b"marker = 'frozen'\n")
    return root, members, _freeze(root, members)


@pytest.mark.parametrize(
    ("change", "error"),
    [
        ("digest", "digest"),
        ("phase", "manifest"),
        ("missing", "member_missing"),
        ("changed", "member_changed"),
        ("extra_file", "member_unlisted"),
        ("cache_dir", "member_unlisted"),
    ],
)
def test_source_refuses_nonexact_freeze(frozen, change, error):
    root, members, pin = frozen
    assert BOOT.verify_source(pin) == members
    if change == "digest":
        pin = "0" * 64
    elif change == "phase":
        pin = _freeze(root, members, schema="H3_DEC3_DATA_SOURCE_V1")
    elif change == "missing":
        (root / OWNER).unlink()
    elif change == "changed":
        (root / OWNER).write_bytes(b"marker = 'changed'")
    elif change == "extra_file":
        (root / "src/thericher_v2/ops/unlisted.pyd").touch()
    else:
        (root / "src/thericher_v2/ops/__pycache__").mkdir()
    with pytest.raises(ValueError, match=f"^dec9_source_{error}$"):
        BOOT.verify_source(pin)


def test_loader_executes_only_the_verified_bytes(frozen):
    root, _, pin = frozen
    loader = BOOT._FrozenImports(BOOT.verify_source(pin))
    (root / OWNER).write_bytes(b"raise AssertionError('reopened source')")
    spec = loader.find_spec("thericher_v2.ops.h3_dec9_target_owner")
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    assert module.marker == "frozen"
    with pytest.raises(ModuleNotFoundError, match="dec9_source_import"):
        loader.find_spec("thericher_v2.ops.h3_dec9_other_owner")


def test_isolated_activation_uses_real_target_owner(tmp_path):
    data_root, market_root = tmp_path / "data", tmp_path / "market"
    root = data_root / "source"
    members = {
        path.relative_to(REPO).as_posix(): path.read_bytes()
        for path in (REPO / "src/thericher_v2").rglob("*.py")
    }
    members[BOOT.ENTRY] = SCRIPT.read_bytes()
    pin = _freeze(root, members)
    prebound_at = ENTRY_OPEN - timedelta(seconds=1)
    pins = Dec9TargetPins(
        owner="thericher-" + BOOT.RUN_NAME,
        source_sha256=pin,
        attempt_sha256=BOOT._sha(f"{BOOT.RUN_NAME}:{pin}".encode("ascii")),
        data_root=data_root,
        market_root=market_root,
        prebound_at=prebound_at,
        capture_opens=BOOT.OPENS,
        capture_closes=BOOT.CLOSES,
        seal_before=BOOT.SEAL_BEFORE,
    )
    direct = BOOT.DIRECT_PYTHONW
    if not direct.is_file():
        direct = Path(sys._base_executable).resolve(strict=True)
    check = """
import importlib.util
import sys
from datetime import datetime
from pathlib import Path
from uuid import UUID
import os

entry, venv, pin, prebound_at, digest, executable, executable_pin = sys.argv[1:]
spec = importlib.util.spec_from_file_location("dec9_test_child", entry)
boot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(boot)
boot.SOURCE = Path(entry).parents[1]
boot.DATA_ROOT = boot.SOURCE.parent
boot.MARKET_ROOT = boot.DATA_ROOT.parent / "market"
boot.VENV = Path(venv)
boot.DIRECT_PYTHONW = Path(executable)
boot.DIRECT_PYTHONW_SHA256 = executable_pin
boot._now = lambda: boot.OPENS
args = {"prebound_at": datetime.fromisoformat(prebound_at)}
try:
    boot.bind_target_owner(pin, target_prebind_sha256="0" * 64, **args)
except ValueError as error:
    assert str(error) == "dec9_owner_prebind"
else:
    raise AssertionError("wrong prebind admitted")
assert not any(boot._project_module(name) for name in sys.modules)
action = boot.NativeAction(boot.TASK_PATH, executable, "", str(boot.SOURCE))
projection = boot.NativeProjection(action, *[c * 64 for c in "abcd"])
prebind = boot.NativePrebind(pin, args["prebound_at"], digest, projection)
birth = f"win-filetime:{boot._ticks(boot.OPENS)}"
bind = boot.bind_target_owner

class StopBeforeNetwork(Exception):
    pass

class Host:
    roles = []
    roots = (boot.DATA_ROOT / "run", boot.MARKET_ROOT, boot.DATA_ROOT / "run/capture")

    def prove(self):
        assert tuple(path.exists() for path in self.roots) == tuple(
            index < len(self.roles) for index in range(len(self.roots))
        ), "ordinary readiness called during mkdir-to-registration transition"
        return boot.NativeOwnerProof(projection, prebind.sha256, UUID(int=1), os.getpid(), birth)

    def register_created_root(self, proof, role, path, identity):
        assert proof == boot.NativeOwnerProof(
            projection, prebind.sha256, UUID(int=1), os.getpid(), birth
        )
        assert path == self.roots[len(self.roles)]
        assert tuple(root.exists() for root in self.roots) == tuple(
            index <= len(self.roles) for index in range(len(self.roots))
        )
        info = path.stat()
        assert identity == (info.st_dev, info.st_ino)
        self.roles.append(role)
        return True

    def load_paper_market_data_config(self, scope):
        from thericher_v2.execution.kis_market_data import KisPaperMarketDataConfig
        assert scope == projection.config_scope_sha256
        assert (boot.DATA_ROOT / "run/owner/ATTEMPT.json").is_file()
        assert self.roles == ["run", "market", "capture"]
        return KisPaperMarketDataConfig("invented-key", "invented-secret")

def bind_with_synthetic_capture(*a, **kw):
    bound = bind(*a, **kw)
    from thericher_v2.ops import h3_dec9_fixed_half_capture, h3_dec9_target_owner as owner
    from thericher_v2.execution import paper_peer_visit
    assert bound.run_owner is owner.run_dec9_target_owner
    assert bound.pins.prebind_sha256 == bound.prebind_sha256 == digest

    def no_network(**kwargs):
        assert kwargs["owner_ready"]().ready is True
        for path in (kwargs["market_root"], kwargs["artifact_root"]):
            path.mkdir()
            info = path.stat()
            assert kwargs["on_root_created"](path, (info.st_dev, info.st_ino)) is True
        assert kwargs["config_loader"]().app_key == "invented-key"
        raise StopBeforeNetwork

    paper_peer_visit.process_start = h3_dec9_fixed_half_capture.process_start = lambda pid: birth
    owner.capture_h3_daily_panel_once = no_network
    return bound

boot.bind_target_owner = bind_with_synthetic_capture
try:
    boot.activate_target_owner(prebind, native_prebind_sha256=prebind.sha256, host=Host())
except StopBeforeNetwork:
    pass
else:
    raise AssertionError("real owner did not reach the synthetic capture boundary")
"""
    subprocess.run(
        [
            str(direct),
            "-I",
            "-S",
            "-B",
            "-c",
            check,
            str(root / BOOT.ENTRY),
            sys.prefix,
            pin,
            prebound_at.isoformat(),
            pins.prebind_sha256,
            str(direct),
            BOOT._sha(direct.read_bytes()),
        ],
        check=True,
        timeout=30,
    )
    attempt = json.loads((data_root / "run/owner/ATTEMPT.json").read_bytes())
    assert attempt["target_prebind_sha256"] == pins.prebind_sha256
    assert not (data_root / "run/OWNER-CLOSED.json").exists()
    assert market_root.is_dir()


@pytest.mark.parametrize(
    "fault", [None, "shim", "base_redirect", "changed", "link", "not_isolated"]
)
def test_runtime_requires_direct_pinned_image(tmp_path, monkeypatch, fault):
    root = tmp_path / "source"
    binary = tmp_path / "pythonw.exe"
    binary.write_bytes(b"synthetic image")
    shim = tmp_path / "shim.exe"
    pin = BOOT._sha(binary.read_bytes())
    fake_sys = SimpleNamespace(
        executable=str(shim if fault == "shim" else binary),
        _base_executable=str(shim if fault == "base_redirect" else binary),
        flags=SimpleNamespace(isolated=fault != "not_isolated", no_site=True),
        dont_write_bytecode=True,
        modules={},
    )
    monkeypatch.setattr(BOOT, "sys", fake_sys)
    monkeypatch.setattr(BOOT, "SOURCE", root)
    monkeypatch.setattr(BOOT, "__file__", str(root / BOOT.ENTRY))
    monkeypatch.setattr(BOOT, "DIRECT_PYTHONW", binary)
    monkeypatch.setattr(BOOT, "DIRECT_PYTHONW_SHA256", pin)
    if fault == "changed":
        binary.write_bytes(b"drift")
    if fault == "link":
        os.link(binary, shim)
    try:
        if fault is None:
            BOOT._require_runtime()
        else:
            with pytest.raises(ValueError, match="^dec9_owner_runtime$"):
                BOOT._require_runtime()
    finally:
        if fault == "link":
            shim.unlink()


@pytest.fixture
def activation(frozen, monkeypatch):
    root, _, pin = frozen
    action = BOOT.NativeAction(BOOT.TASK_PATH, str(root / "host.exe"), "--fixed", str(root))
    projection = BOOT.NativeProjection(action, *[c * 64 for c in "abcd"])
    prebind = BOOT.NativePrebind(pin, ENTRY_OPEN - timedelta(seconds=1), "e" * 64, projection)
    birth = f"win-filetime:{BOOT._ticks(BOOT.OPENS)}"

    class Host:
        now = BOOT.OPENS
        proof = BOOT.NativeOwnerProof(projection, prebind.sha256, UUID(int=1), os.getpid(), birth)
        proof_calls = 0
        config_calls = 0
        config = KisPaperMarketDataConfig("invented-key", "invented-secret")
        native_birth = birth
        registrations = None

        def prove(self):
            self.proof_calls += 1
            return self.proof

        def register_created_root(self, proof, role, path, identity):
            assert proof == self.proof
            self.registrations.append((role, path, identity))
            return True

        def load_paper_market_data_config(self, scope):
            assert scope == projection.config_scope_sha256
            self.config_calls += 1
            return self.config

    host = Host()
    host.registrations = []
    monkeypatch.setattr(BOOT, "DATA_ROOT", root.parent)
    monkeypatch.setattr(BOOT, "MARKET_ROOT", root.parent / "market")
    monkeypatch.setattr(BOOT, "DIRECT_PYTHONW", Path(action.executable))
    monkeypatch.setattr(BOOT, "_now", lambda: host.now)
    monkeypatch.setattr(BOOT, "_require_runtime", lambda: None)
    monkeypatch.setattr(paper_peer_visit, "process_start", lambda _pid: host.native_birth)

    def forbidden(*args, **kwargs):
        pytest.fail("binding reached with denied native preflight")

    monkeypatch.setattr(BOOT, "bind_target_owner", forbidden)
    return prebind, host


@pytest.mark.parametrize(
    "fault",
    [
        "pin",
        "action",
        "definition",
        "runtime",
        "acl",
        "config_scope",
        "proof_pin",
        "pid",
        "birth",
        "bool",
    ],
)
def test_activation_denies_unbound_native_proof(activation, fault):
    prebind, host = activation
    pin = prebind.sha256
    if fault == "pin":
        # The digest independently retained before launch cannot be rebuilt from the changed action.
        projection = prebind.projection
        action = projection.action._replace(arguments="--other")
        prebind = prebind._replace(projection=projection._replace(action=action))
    elif fault in {"action", "definition", "runtime", "acl", "config_scope"}:
        projection = host.proof.projection
        change = {
            "action": {"action": projection.action._replace(arguments="--other")},
            "definition": {"definition_sha256": "0" * 64},
            "runtime": {"runtime_sha256": "0" * 64},
            "acl": {"custody_acl_sha256": "0" * 64},
            "config_scope": {"config_scope_sha256": "0" * 64},
        }[fault]
        host.proof = host.proof._replace(projection=projection._replace(**change))
    elif fault == "proof_pin":
        host.proof = host.proof._replace(prebind_sha256="0" * 64)
    elif fault == "pid":
        host.proof = host.proof._replace(pid=os.getpid() + 1)
    elif fault == "birth":
        host.proof = host.proof._replace(birth=f"win-filetime:{BOOT._ticks(BOOT.OPENS) - 1}")
    else:
        host.proof = True
    error = "prebind" if fault == "pin" else "owner"
    with pytest.raises(ValueError, match=f"^dec9_native_{error}$"):
        BOOT.activate_target_owner(prebind, native_prebind_sha256=pin, host=host)
    assert host.config_calls == 0


def test_activation_without_config_provider_never_binds_owner(activation):
    prebind, host = activation
    host.load_paper_market_data_config = None
    with pytest.raises(ValueError, match="^dec9_native_config$"):
        BOOT.activate_target_owner(prebind, native_prebind_sha256=prebind.sha256, host=host)


def test_activation_without_registrar_never_binds_owner(activation):
    prebind, host = activation
    host.register_created_root = None
    with pytest.raises(ValueError, match="^dec9_native_root_registration$"):
        BOOT.activate_target_owner(prebind, native_prebind_sha256=prebind.sha256, host=host)
    assert host.config_calls == 0


@pytest.mark.parametrize(
    "fault",
    [None, "instance", "birth", "source", "late", "seal_cutoff", "config_type", "config_drift"],
)
def test_activation_rechecks_owner_and_loads_config_only_in_capture(activation, monkeypatch, fault):
    prebind, host = activation
    pins = object()
    close_digest = "f" * 64

    if fault == "config_drift":
        load = host.load_paper_market_data_config

        def config_with_drift(scope):
            config = load(scope)
            host.proof = host.proof._replace(instance=UUID(int=2))
            return config

        host.load_paper_market_data_config = config_with_drift

    def owner(passed, *, prebind_sha256, clock, owner_ready, register_created_root, config_loader):
        assert passed is pins and prebind_sha256 == prebind.target_prebind_sha256
        assert host.config_calls == 0 and type(owner_ready()) is CaptureReadiness
        run = BOOT.DATA_ROOT / "run"
        for index, (role, path) in enumerate(
            (("run", run), ("market", BOOT.MARKET_ROOT), ("capture", run / "capture")), 1
        ):
            assert register_created_root(role, path, (1, index)) is True
        assert len(host.registrations) == 3
        if fault == "instance":
            original = host.proof
            host.proof = original._replace(instance=UUID(int=2))
            assert not owner_ready().ready
            host.proof = original  # An observed loss cannot be treated as a transient readiness.
        elif fault == "birth":
            host.native_birth = None
        elif fault == "source":
            (BOOT.SOURCE / "SOURCE.json").write_bytes(b"changed")
        elif fault == "late":
            host.now = BOOT.CLOSES
            assert owner_ready().ready  # Sealing is still allowed, credential loading is not.
        elif fault == "seal_cutoff":
            host.now = BOOT.SEAL_BEFORE
            assert not owner_ready().ready
        elif fault == "config_type":
            host.config = object()
        elif fault is None:
            assert config_loader() is host.config
            with pytest.raises(ValueError, match="dec9_native_config"):
                config_loader()
            host.now = BOOT.CLOSES
            assert clock() == BOOT.CLOSES and owner_ready().ready
            return close_digest
        config_loader()
        pytest.fail("denied config returned")

    def bind(pin, *, prebound_at, target_prebind_sha256):
        assert (pin, prebound_at, target_prebind_sha256) == prebind[:3]
        return BOOT.TargetOwnerBinding(owner, pins, target_prebind_sha256)

    monkeypatch.setattr(BOOT, "bind_target_owner", bind)
    if fault is None:
        assert (
            BOOT.activate_target_owner(prebind, native_prebind_sha256=prebind.sha256, host=host)
            == close_digest
        )
    else:
        with pytest.raises(ValueError, match="dec9_native_config|dec9_owner_clock"):
            BOOT.activate_target_owner(prebind, native_prebind_sha256=prebind.sha256, host=host)
    assert host.config_calls == int(fault in {None, "config_type", "config_drift"})


@pytest.mark.parametrize(
    "fault", ["incomplete", "wrong_path", "truthy", "exception", "proof_drift"]
)
def test_activation_registration_denial_blocks_config(activation, monkeypatch, fault):
    prebind, host = activation
    run = BOOT.DATA_ROOT / "run"

    def registrar(*_args):
        if fault == "proof_drift":
            host.proof = host.proof._replace(instance=UUID(int=2))
            return True
        if fault == "exception":
            raise RuntimeError("invented internal detail")
        if fault == "wrong_path":
            pytest.fail("registrar called for a wrong path")
        return 1

    host.register_created_root = registrar

    def owner(_pins, *, register_created_root, config_loader, owner_ready, **_kwargs):
        if fault != "incomplete":
            with pytest.raises(ValueError, match="^dec9_native_root_registration$"):
                register_created_root("run", run if fault != "wrong_path" else run.parent, (1, 2))
            assert not owner_ready().ready
        config_loader()

    monkeypatch.setattr(
        BOOT,
        "bind_target_owner",
        lambda *_args, **_kwargs: BOOT.TargetOwnerBinding(owner, None, ""),
    )
    with pytest.raises(ValueError, match="^dec9_native_config$"):
        BOOT.activate_target_owner(prebind, native_prebind_sha256=prebind.sha256, host=host)
    assert host.config_calls == 0


def test_bootstrap_is_not_an_executable_dispatch():
    completed = subprocess.run(
        [sys.executable, "-I", "-S", "-B", str(SCRIPT)], check=False, timeout=10
    )
    assert completed.returncode == 20

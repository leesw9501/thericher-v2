"""Bind the Dec9 target-only Data owner to a protected native host."""

import hashlib
import importlib.abc
import importlib.util
import json
import os
import re
import stat
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import NamedTuple, Protocol
from uuid import UUID

RUN_NAME = "h3-dec9-modp1-target-owner-20261209-v1"
TASK_PATH = "\\thericher-" + RUN_NAME
SOURCE_SCHEMA = "H3_DEC9_TARGET_SOURCE_V1"
DATA_ROOT = Path(f"D:/thericher-v2/model-artifacts/data/{RUN_NAME}")
MARKET_ROOT = Path(f"D:/market_data/us_equities/kis_paper_private/{RUN_NAME}")
SOURCE = DATA_ROOT / "source"
VENV = Path("C:/Users/Public/Documents/thericher-v2/.venv")
DIRECT_PYTHONW = Path(
    "C:/Users/User/AppData/Roaming/uv/python/"
    "cpython-3.14.3-windows-x86_64-none/pythonw.exe"
)
DIRECT_PYTHONW_SHA256 = "3737f863a02f4c92387dee920aeee6ab260548cd7c4bed829e96ed005e65409e"
OPENS = datetime(2026, 12, 9, 21, 30, tzinfo=UTC)
CLOSES = datetime(2026, 12, 9, 21, 40, tzinfo=UTC)
SEAL_BEFORE = datetime(2026, 12, 9, 21, 45, tzinfo=UTC)
ENTRY = "scripts/run_h3_dec9_target_owner.py"
_MEMBER = re.compile(r"src/thericher_v2/(?:[a-zA-Z_][a-zA-Z_0-9]*/)*[a-zA-Z_][a-zA-Z_0-9]*\.py")
_REQUIRED = {
    ENTRY,
    "src/thericher_v2/__init__.py",
    "src/thericher_v2/ops/__init__.py",
    "src/thericher_v2/ops/h3_dec9_target_owner.py",
    "src/thericher_v2/ops/h3_dec9_fixed_half_capture.py",
    "src/thericher_v2/ops/h3_dec9_fixed_half_target.py",
}


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _hex(value, digits=64):
    return type(value) is str and re.fullmatch(rf"[0-9a-f]{{{digits}}}", value) is not None


def _plain(info, *, directory=False):
    kind = stat.S_ISDIR if directory else stat.S_ISREG
    return (
        kind(info.st_mode)
        and not (getattr(info, "st_file_attributes", 0) & 0x400)
        and (directory or info.st_nlink == 1)
    )


def _read(path, limit):
    before = path.lstat()
    if not _plain(before):
        raise ValueError("dec9_source_path")
    with path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        if not _plain(opened) or _identity(opened) != _identity(before):
            raise ValueError("dec9_source_path")
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("dec9_source_size")
    after = path.lstat()
    if not _plain(after) or _identity(after) != _identity(before) or len(raw) != before.st_size:
        raise ValueError("dec9_source_member_changed")
    return raw


def _identity(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def _unique_object(items):
    result = dict(items)
    if len(result) != len(items):
        raise ValueError("dec9_source_manifest")
    return result


def _walk_error(error):
    raise error


def verify_source(source_sha256):
    """Return the hashed bytes of the complete fixed-phase import tree."""
    root = SOURCE
    if not _hex(source_sha256):
        raise ValueError("dec9_source_digest")
    if (
        not root.is_absolute()
        or not all(_plain(path.lstat(), directory=True) for path in (root, *root.parents))
        or root.resolve(strict=True) != root
    ):
        raise ValueError("dec9_source_root")
    raw = _read(root / "SOURCE.json", 1024 * 1024)
    if _sha(raw) != source_sha256:
        raise ValueError("dec9_source_digest")
    manifest = json.loads(raw, object_pairs_hook=_unique_object)
    if (
        type(manifest) is not dict
        or manifest.keys() != {"schema", "run", "tree", "files"}
        or manifest["schema"] != SOURCE_SCHEMA
        or manifest["run"] != RUN_NAME
        or not _hex(manifest["tree"], 40)
        or type(manifest["files"]) is not dict
    ):
        raise ValueError("dec9_source_manifest")
    files = manifest["files"]
    if (
        not _REQUIRED <= files.keys()
        or any(not (key == ENTRY or _MEMBER.fullmatch(key)) for key in files)
        or any(not _hex(digest) for digest in files.values())
        or len({key.casefold() for key in files}) != len(files)
    ):
        raise ValueError("dec9_source_manifest")
    directories = {parent.as_posix() for key in files for parent in Path(key).parents}
    if any(
        f"{directory}/__init__.py" not in files
        for directory in directories
        if directory.startswith("src/thericher_v2")
    ):
        raise ValueError("dec9_source_manifest")

    observed = {}
    for directory, children, names in os.walk(root, onerror=_walk_error, followlinks=False):
        prefix = Path(directory)
        for child in children:
            path = prefix / child
            if path.relative_to(root).as_posix() not in directories or not _plain(
                path.lstat(), directory=True
            ):
                raise ValueError("dec9_source_member_unlisted")
        for name in names:
            path = prefix / name
            key = path.relative_to(root).as_posix()
            if key == "SOURCE.json":
                continue
            if key not in files:
                raise ValueError("dec9_source_member_unlisted")
            data = _read(path, 4 * 1024 * 1024)
            if _sha(data) != files[key]:
                raise ValueError("dec9_source_member_changed")
            observed[key] = data
    if observed.keys() != files.keys():
        raise ValueError("dec9_source_member_missing")
    return observed


class _FrozenImports(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Project imports execute the authenticated buffers, never disk bytecode."""

    def __init__(self, members):
        self._members = members

    def _member(self, fullname):
        stem = "src/" + fullname.replace(".", "/")
        package = stem + "/__init__.py"
        module = stem + ".py"
        if package in self._members and module not in self._members:
            return package, True
        if module in self._members and package not in self._members:
            return module, False
        raise ModuleNotFoundError("dec9_source_import", name=fullname)

    def find_spec(self, fullname, path=None, target=None):
        if fullname != "thericher_v2" and not fullname.startswith("thericher_v2."):
            return None
        key, package = self._member(fullname)
        spec = importlib.util.spec_from_loader(
            fullname, self, origin=str(SOURCE / key), is_package=package
        )
        spec.has_location = True
        return spec

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        key, _ = self._member(module.__name__)
        code = compile(self._members[key], module.__spec__.origin, "exec", dont_inherit=True)
        exec(code, vars(module))


class TargetOwnerBinding(NamedTuple):
    run_owner: object
    pins: object
    prebind_sha256: str


class NativeAction(NamedTuple):
    task_path: str
    executable: str
    arguments: str
    working_directory: str


class NativeProjection(NamedTuple):
    action: NativeAction
    definition_sha256: str
    custody_acl_sha256: str
    runtime_sha256: str
    config_scope_sha256: str


class NativeOwnerProof(NamedTuple):
    projection: NativeProjection
    prebind_sha256: str
    instance: UUID
    pid: int
    birth: str


class ProtectedNativeOwner(Protocol):
    """Only a qualified host may supply these capabilities, never launch arguments.

    Each proof must freshly verify the exact Scheduler definition/action/ACL,
    isolated source and custody, launcher/interpreter/dependencies, config
    access scope, and the live instance's link to this process. Policy digests
    identify nonsecret bindings, not credentials or expected plan echoes.
    """

    def prove(self) -> NativeOwnerProof: ...

    def load_paper_market_data_config(self, config_scope_sha256: str) -> object: ...


class NativePrebind(NamedTuple):
    source_sha256: str
    prebound_at: datetime
    target_prebind_sha256: str
    projection: NativeProjection

    @property
    def sha256(self):
        projection = self.projection
        document = dict(
            schema="H3_DEC9_NATIVE_PREBIND_V1",
            run=RUN_NAME,
            source_sha256=self.source_sha256,
            prebound_at=self.prebound_at.isoformat(),
            target_prebind_sha256=self.target_prebind_sha256,
            action=projection.action._asdict(),
            definition_sha256=projection.definition_sha256,
            custody_acl_sha256=projection.custody_acl_sha256,
            runtime_sha256=projection.runtime_sha256,
            config_scope_sha256=projection.config_scope_sha256,
            capture_opens=OPENS.isoformat(),
            capture_closes=CLOSES.isoformat(),
            seal_before=SEAL_BEFORE.isoformat(),
        )
        return _sha(json.dumps(document, sort_keys=True, separators=(",", ":")).encode("ascii"))


def _projection(value):
    return (
        type(value) is NativeProjection
        and type(value.action) is NativeAction
        and all(type(s) is str and "\0" not in s for s in value.action)
        and value.action.task_path == TASK_PATH
        and value.action.executable == str(DIRECT_PYTHONW)
        and Path(value.action.working_directory).is_absolute()
        and all(map(_hex, value[1:]))
    )


def _project_module(name):
    return name == "thericher_v2" or name.startswith("thericher_v2.")


def _require_runtime():
    if (
        Path(__file__).resolve() != SOURCE / ENTRY
        or Path(sys.executable) != DIRECT_PYTHONW
        or Path(sys._base_executable) != DIRECT_PYTHONW
        or not (sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode)
        or any(map(_project_module, sys.modules))
    ):
        raise ValueError("dec9_owner_runtime")
    try:
        pinned = (
            DIRECT_PYTHONW.resolve(strict=True) == DIRECT_PYTHONW
            and all(_plain(path.lstat(), directory=True) for path in DIRECT_PYTHONW.parents)
            and _sha(_read(DIRECT_PYTHONW, 1024 * 1024)) == DIRECT_PYTHONW_SHA256
        )
    except (OSError, ValueError):
        pinned = False
    if not pinned:
        raise ValueError("dec9_owner_runtime")


def _now():
    return datetime.now(UTC)


def _capture_window():
    if not OPENS <= _now() < CLOSES:
        raise ValueError("dec9_owner_clock")


def _utc(value):
    return type(value) is datetime and value.utcoffset() == UTC.utcoffset(None)


def _ticks(stamp):
    delta = stamp - datetime(1601, 1, 1, tzinfo=UTC)
    return (delta.days * 86400 + delta.seconds) * 10_000_000 + delta.microseconds * 10


def bind_target_owner(source_sha256, *, prebound_at, target_prebind_sha256):
    """Bind only. The protected launcher must still supply native admission.

    This installs the verified importer for the lifetime of a dedicated owner
    process on success. It does not prove launch provenance or root ACLs, read
    credentials, create an attempt, or invoke the owner.
    """
    _require_runtime()
    _capture_window()
    if not _utc(prebound_at) or not _hex(target_prebind_sha256):
        raise ValueError("dec9_owner_prebind")
    finder = _FrozenImports(verify_source(source_sha256))
    _capture_window()
    sys.meta_path.insert(0, finder)
    site_packages = str(VENV / "Lib/site-packages")
    sys.path.append(site_packages)
    try:
        from thericher_v2.ops.h3_dec9_fixed_half_target import Dec9TargetPins
        from thericher_v2.ops.h3_dec9_target_owner import run_dec9_target_owner

        pins = Dec9TargetPins(
            owner="thericher-" + RUN_NAME,
            source_sha256=source_sha256,
            attempt_sha256=_sha(f"{RUN_NAME}:{source_sha256}".encode("ascii")),
            data_root=DATA_ROOT,
            market_root=MARKET_ROOT,
            prebound_at=prebound_at,
            capture_opens=OPENS,
            capture_closes=CLOSES,
            seal_before=SEAL_BEFORE,
        )
        if pins.prebind_sha256 != target_prebind_sha256:
            raise ValueError("dec9_owner_prebind")
        _capture_window()
        return TargetOwnerBinding(run_dec9_target_owner, pins, target_prebind_sha256)
    except BaseException:
        sys.meta_path.remove(finder)
        sys.path.remove(site_packages)
        for name in tuple(sys.modules):
            if _project_module(name):
                del sys.modules[name]
        raise


def activate_target_owner(
    prebind: NativePrebind, *, native_prebind_sha256: str, host: ProtectedNativeOwner
) -> str:
    """In-process continuation for an independently qualified, pinned host.

    This does not implement Windows readback, authenticate the host itself or
    expose an executable action. The independently retained digest must reach
    the host out of band, not be derived from mutable launch input at runtime.
    """
    _require_runtime()
    _capture_window()
    if not (
        type(prebind) is NativePrebind
        and _hex(prebind.source_sha256)
        and _utc(prebind.prebound_at)
        and prebind.prebound_at < OPENS
        and _hex(prebind.target_prebind_sha256)
        and _projection(prebind.projection)
        and _hex(native_prebind_sha256)
        and native_prebind_sha256 == prebind.sha256
    ):
        raise ValueError("dec9_native_prebind")

    pid = os.getpid()

    def prove():
        proof = host.prove()
        now = _now()
        if not (
            OPENS <= now < SEAL_BEFORE
            and type(proof) is NativeOwnerProof
            and _projection(proof.projection)
            and proof.projection == prebind.projection
            and _hex(proof.prebind_sha256)
            and proof.prebind_sha256 == native_prebind_sha256
            and type(proof.instance) is UUID
            and proof.instance.int != 0
            and type(proof.pid) is int
            and proof.pid == pid
            and type(proof.birth) is str
            and re.fullmatch(r"win-filetime:[0-9]{18}", proof.birth)
            and _ticks(OPENS) <= int(proof.birth.split(":")[1]) <= _ticks(now)
        ):
            raise ValueError("dec9_native_owner")
        return proof

    try:
        original = prove()
    except Exception:
        raise ValueError("dec9_native_owner") from None
    load_scoped_config = getattr(host, "load_paper_market_data_config", None)
    if not callable(load_scoped_config):
        raise ValueError("dec9_native_config")
    bound = bind_target_owner(
        prebind.source_sha256,
        prebound_at=prebind.prebound_at,
        target_prebind_sha256=prebind.target_prebind_sha256,
    )
    from thericher_v2.execution.kis_market_data import (
        KIS_PAPER_MARKET_DATA_BASE_URL,
        KisPaperMarketDataConfig,
    )
    from thericher_v2.execution.kis_paper_data_capture import CaptureReadiness
    from thericher_v2.execution.paper_peer_visit import process_start

    lost = False

    def ready():
        nonlocal lost
        if not lost:
            try:
                lost = not (
                    OPENS <= _now() < SEAL_BEFORE
                    and prove() == original
                    and process_start(pid) == original.birth
                    and _sha(_read(SOURCE / "SOURCE.json", 1024 * 1024)) == prebind.source_sha256
                    and OPENS <= _now() < SEAL_BEFORE
                )
            except Exception:
                lost = True
        return CaptureReadiness(not lost)

    config_attempted = False

    def load_config():
        nonlocal config_attempted
        if config_attempted or not ready().ready:
            raise ValueError("dec9_native_config")
        _capture_window()
        config_attempted = True
        try:
            config = load_scoped_config(prebind.projection.config_scope_sha256)
        except Exception:
            raise ValueError("dec9_native_config") from None
        if (
            type(config) is not KisPaperMarketDataConfig
            or config.base_url != KIS_PAPER_MARKET_DATA_BASE_URL
            or not ready().ready
        ):
            raise ValueError("dec9_native_config")
        _capture_window()
        return config

    if not ready().ready:
        raise ValueError("dec9_native_owner")
    _capture_window()
    return bound.run_owner(
        bound.pins,
        prebind_sha256=prebind.target_prebind_sha256,
        clock=_now,
        owner_ready=ready,
        config_loader=load_config,
    )


if __name__ == "__main__":
    # No command-line admission until a protected native launch can be attested.
    raise SystemExit(20)

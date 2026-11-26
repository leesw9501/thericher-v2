"""Bridge the named Dec4 CPU forecast to an independently protected host."""

import hashlib
import json
import os
import re
import stat
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType

STUDY = "h3-dec4-fixed-half-forecast-20261204-v1"
OWNER = "thericher-" + STUDY
SOURCE = Path("D:/thericher-v2/model-artifacts/research") / STUDY / "source"
SOURCE_SCHEMA = "H3_DEC4_FIXED_HALF_SOURCE_V1"
ENTRY = "scripts/run_h3_dec4_fixed_half.py"
SITE_PACKAGES = Path("C:/Users/Public/Documents/thericher-v2/.venv/Lib/site-packages")
OPENS = datetime(2026, 12, 4, 14, 12, tzinfo=UTC)
LAST_START = OPENS.replace(minute=13)
HARD_STOP = OPENS.replace(minute=25)

DATA_SOURCE = Path("D:/thericher-v2/model-artifacts/data/h3-dec3-modp1-owner-20261203-v1/source")
DATA_SOURCE_SHA256 = "878615272a71b035f61438d3242163c50f548350842409e6bc64dd6415b861bf"
DATA_WRITER = "scripts/run_h3_nov27_data_owner.py"
DATA_WRITER_SHA256 = "bdc42ce518780b8b83ac217803fe75c972ece93c89559572706132ad532eeafb"
_MODULE = re.compile(r"src/thericher_v2/(?:[A-Za-z_]\w*/)*[A-Za-z_]\w*\.py", re.ASCII)
_REQUIRED = {
    ENTRY,
    "src/thericher_v2/__init__.py",
    "src/thericher_v2/ops/__init__.py",
    "src/thericher_v2/ops/h3_dec4_fixed_half_plan.py",
    "src/thericher_v2/ops/h3_dec4_point_owner.py",
}


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _hex(value, digits=64):
    return type(value) is str and re.fullmatch(rf"[0-9a-f]{{{digits}}}", value) is not None


def _plain(path, kind):
    info = path.lstat()
    return kind(info.st_mode) and not (getattr(info, "st_file_attributes", 0) & 0x400)


def _directory(path):
    if (
        not path.is_absolute()
        or not all(_plain(p, stat.S_ISDIR) for p in (path, *path.parents))
        or path.resolve(strict=True) != path
    ):
        raise ValueError("dec4_fixed_half_source_path")


def _read(path, limit):
    if not _plain(path, stat.S_ISREG):
        raise ValueError("dec4_fixed_half_source_member")
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("dec4_fixed_half_source_size")
    return raw


def _unique(items):
    result = dict(items)
    if len(result) != len(items):
        raise ValueError("dec4_fixed_half_source_manifest")
    return result


def _walk_error(error):
    raise error


def verify_source(pin):
    """Verify the entire import tree under the protected host's source ACL."""
    _directory(SOURCE)
    raw = _read(SOURCE / "SOURCE.json", 1024 * 1024)
    if not _hex(pin) or _sha(raw) != pin:
        raise ValueError("dec4_fixed_half_source_digest")
    doc = json.loads(raw, object_pairs_hook=_unique)
    if (
        type(doc) is not dict
        or doc.keys() != {"schema", "run", "tree", "files"}
        or doc["schema"] != SOURCE_SCHEMA
        or doc["run"] != STUDY
        or not _hex(doc["tree"], 40)
        or type(doc["files"]) is not dict
    ):
        raise ValueError("dec4_fixed_half_source_manifest")
    files = doc["files"]
    if (
        not _REQUIRED <= files.keys()
        or len(files) > 1024
        or any(not (name == ENTRY or _MODULE.fullmatch(name)) for name in files)
        or any(not _hex(digest) for digest in files.values())
        or len({name.casefold() for name in files}) != len(files)
    ):
        raise ValueError("dec4_fixed_half_source_manifest")
    parents = {p.as_posix() for name in files for p in Path(name).parents}
    if any(f"{p}/__init__.py" not in files for p in parents if p.startswith("src/thericher_v2")):
        raise ValueError("dec4_fixed_half_source_manifest")
    seen = set()
    for directory, children, names in os.walk(SOURCE, onerror=_walk_error):
        prefix = Path(directory)
        for child in children:
            path = prefix / child
            if path.relative_to(SOURCE).as_posix() not in parents or not _plain(path, stat.S_ISDIR):
                raise ValueError("dec4_fixed_half_source_member")
        for name in names:
            path = prefix / name
            key = path.relative_to(SOURCE).as_posix()
            if key == "SOURCE.json":
                continue
            if key not in files or _sha(_read(path, 4 * 1024 * 1024)) != files[key]:
                raise ValueError("dec4_fixed_half_source_member")
            seen.add(key)
    if seen != files.keys():
        raise ValueError("dec4_fixed_half_source_member")


def verify_data_source():
    # The current checkout is not the protected Dec3 writer. Execute only the
    # independently pinned original bytes, then reuse its complete source check.
    writer = DATA_SOURCE / DATA_WRITER
    _directory(writer.parent)
    raw = _read(writer, 64 * 1024)
    if _sha(raw) != DATA_WRITER_SHA256:
        raise ValueError("dec4_fixed_half_data_writer")
    bridge = ModuleType("dec4_fixed_half_pinned_data_bridge")
    exec(compile(raw, str(writer), "exec", dont_inherit=True), vars(bridge))
    if bridge.DEC3_SOURCE != DATA_SOURCE:
        raise ValueError("dec4_fixed_half_data_source")
    bridge.verify_source(DATA_SOURCE, DATA_SOURCE_SHA256, dec3=True)


def _closed_sync_data(pid, birth, digest, *, probe):
    # Same closure rule as the point launcher: probe the authenticated
    # synchronous writer's receipt PID, not the possibly different shim PID.
    if (
        type(pid) is not int
        or not 0 < pid < 2**32
        or type(birth) is not str
        or not re.fullmatch(r"win-filetime:[1-9][0-9]{0,18}", birth)
        or not _hex(digest)
    ):
        return False
    root = DATA_SOURCE.parent / "run"
    _directory(root)
    receipt = root / "OWNER-CLOSED.json"
    raw = _read(receipt, 16_384)
    return _sha(raw) == digest and probe(pid) is None and _read(receipt, 16_384) == raw


def _now():
    return datetime.now(UTC)


def _require_runtime():
    if (
        os.name != "nt"
        or Path(__file__).resolve() != SOURCE / ENTRY
        or not (sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode)
        or any(name == "thericher_v2" or name.startswith("thericher_v2.") for name in sys.modules)
    ):
        raise ValueError("dec4_fixed_half_runtime")


def _bind_core():
    sys.path.insert(0, str(SOURCE / "src"))
    sys.path.append(str(SITE_PACKAGES))
    from thericher_v2.execution.paper_peer_visit import process_start
    from thericher_v2.ops import h3_dec4_fixed_half_plan as core
    from thericher_v2.ops import h3_dec4_point_owner as data

    if (
        (core.STUDY, core.OPENS, core.LAST_START, core.HARD_STOP)
        != (STUDY, OPENS, LAST_START, HARD_STOP)
        or (data._RESEARCH / STUDY / "source", data._DATA / "source") != (SOURCE, DATA_SOURCE)
        or (data.DATA_SOURCE_SHA256, data._WRITER, data._WRITER_SHA)
        != (DATA_SOURCE_SHA256, DATA_WRITER, DATA_WRITER_SHA256)
    ):
        raise ValueError("dec4_fixed_half_core_binding")
    return core.run_dec4_fixed_half_forecast, process_start


def run_fixed_half_owner(source_sha256, *, host_ready):
    """Run once in a dedicated protected host and return the core seal digest.

    The host supplies an independently prebound source pin and a fresh literal
    True only for the named owner: same instance, protected source/runtime and
    output parent, read-only Data/model paths, and no network or credentials.
    The host owns one-attempt admission, hard tree termination and independent
    exit/digest retention before HARD_STOP. This bridge cannot prove those.
    """
    last = OPENS

    def gate(before):
        nonlocal last
        now = _now()
        if not last <= now < before:
            raise ValueError("dec4_fixed_half_launcher_clock")
        if host_ready() is not True:
            raise ValueError("dec4_fixed_half_launcher_host")
        after = _now()
        if not now <= after < before:
            raise ValueError("dec4_fixed_half_launcher_clock")
        last = after
        return after

    gate(LAST_START)
    _require_runtime()
    verify_source(source_sha256)
    gate(LAST_START)
    verify_data_source()
    gate(LAST_START)
    forecast, process_start = _bind_core()
    pid = os.getpid()
    born = process_start(pid)
    if type(born) is not str or not re.fullmatch(r"win-filetime:[1-9][0-9]{0,18}", born):
        raise ValueError("dec4_fixed_half_launcher_process")

    def ready():
        gate(HARD_STOP)
        return (
            process_start(pid) == born
            and _sha(_read(SOURCE / "SOURCE.json", 1024 * 1024)) == source_sha256
        )

    def data_closed(pid, birth, digest):
        return _closed_sync_data(pid, birth, digest, probe=process_start)

    gate(LAST_START)
    digest = forecast(
        forecast_source_sha256=source_sha256,
        clock=_now,
        owner_ready=ready,
        data_owner_closed=data_closed,
    )
    if not _hex(digest) or not ready():
        raise ValueError("dec4_fixed_half_launcher_result")
    gate(HARD_STOP)
    return digest


if __name__ == "__main__":
    # No command-line admission until a protected host binds this owner.
    raise SystemExit(20)

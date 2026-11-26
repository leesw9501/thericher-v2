"""Read-only H20 phase guest for a newly qualified offline owner channel."""

import argparse
import hashlib
import json
import re
import stat
import sys
from datetime import UTC, datetime
from pathlib import Path

_SOURCE = Path("/reader/SOURCE.json")
_CONTRACT = Path("/contract.json")
_ROOT = Path("/app/private/canary")
_SCHEMA = "H20_PHASE_READER_GUEST_SOURCE_V1"
_CODE_ROOTS = tuple(Path(p) for p in ("/reader", "/legacy", "/h20-sdk", "/h20-source"))
_REQUIRED = {
    "/reader/guest.py",
    "/reader/reader.py",
    "/legacy/read.py",
    "/legacy/access.py",
    "/h20-source/owner_channel.py",
    "/h20-sdk/thericher_v2/ops/h20_exact_phase_outcomes.py",
    "/contract.json",
}


def _need(ok):
    if not ok:
        raise ValueError("H20_PHASE_GUEST_NOT_ADMITTED")


def _read(path):
    _need(not any(p.is_symlink() or p.is_junction() for p in (path, *path.parents)))
    before = path.stat()
    _need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and 0 < before.st_size <= 2**20)
    raw = path.read_bytes()
    after = path.stat()

    def identity(s):
        return s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_nlink

    _need(identity(before) == identity(after) and len(raw) == before.st_size)
    return raw, identity(before)


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _unique(pairs):
    value = {}
    for key, item in pairs:
        _need(key not in value)
        value[key] = item
    return value


def _code_members(roots, pins):
    """Reject import shadowing even when the extra module is not named in the manifest."""
    pending = list(roots)
    count = 0
    while pending:
        folder = pending.pop()
        _need(not folder.is_symlink() and not folder.is_junction() and folder.is_dir())
        for path in folder.iterdir():
            count += 1
            _need(count <= 8192 and not path.is_symlink() and not path.is_junction())
            if path.is_dir():
                pending.append(path)
            elif path.suffix.lower() in {".py", ".pyc", ".so", ".pyd", ".zip"}:
                _need(str(path) in pins)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-sha256")
    parser.add_argument("--read", action="store_true")
    args = parser.parse_args()
    if not args.read:
        print('{"status":"INERT_SOURCE_ONLY","actual_private_reads":0}')
        return
    _need(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode)
    _need(type(args.source_sha256) is str and re.fullmatch("[a-f0-9]{64}", args.source_sha256))
    _need({item.name for item in Path("/sys/class/net").iterdir()} == {"lo"})
    raw_source = _read(_SOURCE)
    _need(_digest(raw_source[0]) == args.source_sha256)
    doc = json.loads(raw_source[0], object_pairs_hook=_unique)
    _need(set(doc) == {"schema", "guest_members"} and doc["schema"] == _SCHEMA)
    pins = doc["guest_members"]
    _need(type(pins) is dict and _REQUIRED <= pins.keys() and len(pins) <= 2048)

    def source_members():
        _code_members(_CODE_ROOTS, pins)
        records = {}
        for name, pin in pins.items():
            _need(
                name == "/contract.json"
                or re.fullmatch(r"/(?:reader|legacy|h20-sdk|h20-source)/[A-Za-z0-9_./-]+", name)
            )
            path = Path(name)
            _need(str(path) == name and ".." not in path.parts)
            raw, mark = _read(path)
            _need(_digest(raw) == pin)
            records[name] = mark
        _need(_read(_SOURCE) == raw_source)
        return records

    source_members()
    sys.path[:0] = ["/reader", "/h20-sdk", "/h20-source", "/legacy"]
    from read import guard

    sys.addaudithook(guard)
    from access import inventory, unchanged
    from owner_channel import OwnerAdmission

    from thericher_v2.ops.h20_exact_phase_outcomes import _load, read_h20_phase_outcomes

    def source_check():
        return source_members(), inventory(Path("/reader")), inventory(Path("/h20-sdk"))

    source_check()
    reader = _load(_read(Path("/reader/reader.py"))[0])
    contract = reader["decode_contract"](json.loads(_read(_CONTRACT)[0], object_pairs_hook=_unique))
    as_of = datetime.now(UTC)
    _need(as_of >= contract.entry_starts_at)
    _need(json.loads(sys.stdin.buffer.readline(4097), object_pairs_hook=_unique) == {})
    admission = OwnerAdmission(sys.stdin.buffer, sys.stdout)

    def admit():
        admission()
        return True

    result = read_h20_phase_outcomes(
        _ROOT,
        contract,
        as_of,
        source_check=source_check,
        inventory=inventory,
        unchanged=unchanged,
        admit=admit,
    )
    print(json.dumps(result, allow_nan=False), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print('{"status":"UNKNOWN_PHASE_READER_NOT_ADMITTED"}', flush=True)
        raise SystemExit(20) from None

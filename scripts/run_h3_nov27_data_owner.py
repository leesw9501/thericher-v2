"""Quiet, once-only Nov27 market-data owner for the Nov30 H3 READY input."""

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType

RUN_NAME = "h3-nov27-modp1-owner-20261127-v1"
OPENS = datetime(2026, 11, 27, 18, 30, tzinfo=UTC)
CLOSES = datetime(2026, 11, 27, 18, 40, tzinfo=UTC)
HARD_STOP = datetime(2026, 11, 27, 18, 45, tzinfo=UTC)
SOURCE = Path(f"D:/thericher-v2/model-artifacts/data/{RUN_NAME}/source")
MARKET = Path(f"D:/market_data/us_equities/kis_paper_private/{RUN_NAME}")
DOTENV = Path("C:/Users/Public/Documents/thericher-v2/.env")
VENV = DOTENV.parent / ".venv"
PINNED_CODE = {
    "pinned/peer_math.py": "fc8df2845ff9de4a9a702ed4a0dff6e7ced298a131dcf6a0c7dbf4210785a0fb",
    "pinned/half_inference.py": "293be34fe5a62b70fc182828b5e920b7035b60293a5aa0b9d3ac2f043dea2a37",
    "pinned/contract.py": "075e9c5ddf495ef9e59d83d08f298ab840e0507b8a92d626387a902d33da003e",
}


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _plain(path):
    info = path.lstat()
    return not (getattr(info, "st_file_attributes", 0) & 0x400) and not stat.S_ISLNK(info.st_mode)


def verify_source(root, pin):
    """Authenticate the complete isolated import tree before importing project code."""
    if not root.is_absolute() or root.resolve(strict=True) != root:
        raise ValueError("nov27_source_root")
    if not all(_plain(p) for p in (root, *root.parents)):
        raise ValueError("nov27_source_root")
    document = root / "SOURCE.json"
    if not _plain(document) or document.stat().st_size > 1024 * 1024:
        raise ValueError("nov27_source_manifest")
    raw = document.read_bytes()
    if _sha(raw) != pin:
        raise ValueError("nov27_source_digest")
    manifest = json.loads(raw)
    files = manifest.get("files")
    if (
        manifest.keys() != {"schema", "run", "tree", "files"}
        or manifest["schema"] != "H3_NOV27_DATA_SOURCE_V1"
        or manifest["run"] != RUN_NAME
        or re.fullmatch(r"[0-9a-f]{40}", manifest["tree"]) is None
        or type(files) is not dict
        or not all(files.get(p) == digest for p, digest in PINNED_CODE.items())
        or "scripts/run_h3_nov27_data_owner.py" not in files
        or "src/thericher_v2/__init__.py" not in files
    ):
        raise ValueError("nov27_source_manifest")
    observed = set()
    pinned = {}
    for directory, children, names in os.walk(root, followlinks=False):
        prefix = Path(directory)
        if not all(_plain(prefix / name) for name in (*children, *names)):
            raise ValueError("nov27_source_reparse")
        for name in names:
            path = prefix / name
            key = path.relative_to(root).as_posix()
            if key == "SOURCE.json":
                continue
            if key not in PINNED_CODE and not (
                key == "scripts/run_h3_nov27_data_owner.py" or key.startswith("src/thericher_v2/")
            ):
                raise ValueError("nov27_source_member_unlisted")
            if not key.endswith(".py") or key not in files or not path.is_file():
                raise ValueError("nov27_source_member_unlisted")
            data = path.read_bytes()
            if _sha(data) != files[key]:
                raise ValueError("nov27_source_member_changed")
            observed.add(key)
            if key in PINNED_CODE:
                pinned[key] = data
    if observed != files.keys():
        raise ValueError("nov27_source_member_missing")
    return pinned


def _load(name, raw):
    module = ModuleType(name)
    sys.modules[name] = module
    exec(compile(raw, f"<pinned {name}>", "exec"), vars(module))
    return module


def _write(path, payload):
    with path.open("xb") as stream:
        stream.write(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("ascii"))
        stream.flush()
        os.fsync(stream.fileno())


def _allowed(at, boundary=CLOSES):
    return type(at) is datetime and at.utcoffset() == UTC.utcoffset(None) and OPENS <= at < boundary


def run_owner(source, source_pin, *, clock):
    """No secret access before the real window, source and exclusive local claim."""
    if not _allowed(clock()):
        raise ValueError("nov27_owner_clock")
    pinned = verify_source(source, source_pin)
    if not _allowed(clock()):
        raise ValueError("nov27_owner_clock")

    sys.path.insert(0, str(source / "src"))
    from thericher_v2.data.kis_paper_h3_producer import produce_nov27_h3_publisher_input_once
    from thericher_v2.execution.kis_market_data import load_kis_paper_market_data_config
    from thericher_v2.execution.kis_paper_data_capture import CaptureReadiness

    _load("peer_math", pinned["pinned/peer_math.py"])
    features = _load("nov27_pinned_features", pinned["pinned/half_inference.py"])
    parser = _load("nov27_pinned_contract", pinned["pinned/contract.py"])
    usage = shutil.disk_usage(MARKET.anchor)
    if not _allowed(clock()) or usage.free * 100 < 15 * usage.total:
        raise ValueError("nov27_owner_admission")

    run = source.parent / "run"
    run.mkdir(exist_ok=False)
    claim = run / "ATTEMPT.json"
    _write(claim, dict(source=source_pin, run=RUN_NAME, started_at=clock().isoformat()))
    claim_digest = _sha(claim.read_bytes())

    def ready():
        return CaptureReadiness(
            _allowed(clock())
            and _plain(claim)
            and _sha(claim.read_bytes()) == claim_digest
            and _sha((source / "SOURCE.json").read_bytes()) == source_pin
        )

    def settings():
        if not ready().ready:
            raise ValueError("nov27_owner_admission")
        return load_kis_paper_market_data_config(DOTENV, environment={})

    try:
        produced = produce_nov27_h3_publisher_input_once(
            market_root=MARKET,
            artifact_root=run / "capture",
            input_root=run / "input",
            data_source_sha256=source_pin,
            synthetic=False,
            clock=clock,
            owner_ready=ready,
            config_loader=settings,
            prefix_features=features.prefix_features,
            parse_input=parser.parse_input,
        )
        closed = clock()
        if not _allowed(closed, HARD_STOP):
            raise ValueError("nov27_owner_publication_cutoff")
        _write(
            run / "OWNER-CLOSED.json",
            dict(
                schema="H3_NOV27_OWNER_CLOSED_V1",
                source=source_pin,
                attempt_sha256=claim_digest,
                ready_sha256=produced.ready_sha256,
                closed_at=closed.isoformat(),
                read_only=True,
                paper_only=True,
            ),
        )
    except Exception:
        _write(
            run / "FAILED.json",
            dict(source=source_pin, status="capture_or_publication_unconfirmed"),
        )
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-sha256", required=True)
    args = parser.parse_args()
    if (
        Path(__file__).resolve() != (SOURCE / "scripts/run_h3_nov27_data_owner.py")
        or Path(sys.executable).resolve() != (VENV / "Scripts/pythonw.exe").resolve()
        or not (sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode)
    ):
        return 20
    sys.path.append(str(VENV / "Lib/site-packages"))
    try:
        run_owner(SOURCE, args.source_sha256, clock=lambda: datetime.now(UTC))
    except Exception:
        return 20
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

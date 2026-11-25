"""Quiet finite H3 capture and credential-free forecast owners."""

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
FORECAST_NAME = "h3-nov30-fixed-half-forecast-20261130-v1"
FORECAST_SOURCE = Path(f"D:/thericher-v2/model-artifacts/research/{FORECAST_NAME}/source")
FORECAST_OPENS = datetime(2026, 11, 30, 14, 12, tzinfo=UTC)
FORECAST_LAST_START = datetime(2026, 11, 30, 14, 13, tzinfo=UTC)
DEC3_NAME = "h3-dec3-modp1-owner-20261203-v1"
DEC3_SOURCE = Path(f"D:/thericher-v2/model-artifacts/data/{DEC3_NAME}/source")
DEC3_MARKET = Path(f"D:/market_data/us_equities/kis_paper_private/{DEC3_NAME}")
DEC3_OPENS = datetime(2026, 12, 3, 21, 30, tzinfo=UTC)
DEC3_LAST_START = datetime(2026, 12, 3, 21, 31, tzinfo=UTC)
DEC3_CAPTURE_END = datetime(2026, 12, 3, 21, 40, tzinfo=UTC)
DEC3_HARD_STOP = datetime(2026, 12, 3, 21, 45, tzinfo=UTC)
POINT_NAME = "h3-dec4-lstm-point-20261204-v1"
POINT_SOURCE = Path(f"D:/thericher-v2/model-artifacts/research/{POINT_NAME}/source")
POINT_OPENS = datetime(2026, 12, 3, 21, 47, tzinfo=UTC)
POINT_LAST_START = datetime(2026, 12, 3, 21, 52, tzinfo=UTC)
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


def verify_source(root, pin, *, forecast=False, dec3=False, point=False):
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
        or manifest["schema"]
        != (
            "H3_DEC4_POINT_SOURCE_V1"
            if point
            else "H3_DEC3_DATA_SOURCE_V1"
            if dec3
            else "H3_NOV30_FORECAST_SOURCE_V1"
            if forecast
            else "H3_NOV27_DATA_SOURCE_V1"
        )
        or manifest["run"]
        != (POINT_NAME if point else DEC3_NAME if dec3 else FORECAST_NAME if forecast else RUN_NAME)
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


def run_forecast(source, source_pin, *, clock):
    if not FORECAST_OPENS <= clock() < FORECAST_LAST_START:
        raise ValueError("nov30_owner_clock")
    pinned = verify_source(source, source_pin, forecast=True)
    sys.path.insert(0, str(source / "src"))
    from thericher_v2.ops.h3_nov30_run import run_nov30_forecast

    parser = _load("nov30_pinned_contract", pinned["pinned/contract.py"])
    run_nov30_forecast(
        SOURCE.parent,
        source.parent / "run",
        forecast_pin=source_pin,
        clock=clock,
        validate_input=parser.validate_input,
    )


def dec3_plan(source, source_pin, prebound_at):
    """Resolve fixed paths; the installer binds the pre-launch target digest."""
    from thericher_v2.ops.h3_dec4_run import Dec4H3Run
    from thericher_v2.research.prospective_h3_target_custody import Nov30H3TargetPins

    run_root = source.parent / "run"
    run = Dec4H3Run(
        DEC3_MARKET,
        run_root / "capture",
        run_root / "input",
        run_root / "point",
        source_pin,
        False,
    )
    target = Nov30H3TargetPins(
        owner="thericher-" + DEC3_NAME,
        source_sha256=source_pin,
        attempt_sha256=_sha(f"{DEC3_NAME}:{source_pin}".encode("ascii")),
        market_root=run.market_root,
        artifact_root=run.artifact_root,
        target_root=run_root / "target",
        prebound_at=prebound_at,
        release_at=datetime(2026, 12, 28, 21, tzinfo=UTC),
        synthetic=False,
    )
    return run_root, run, target


def run_dec3(source, source_pin, *, prebound_at, target_digest, clock):
    if not DEC3_OPENS <= clock() < DEC3_LAST_START:
        raise ValueError("dec3_owner_clock")
    pinned = verify_source(source, source_pin, dec3=True)
    sys.path.insert(0, str(source / "src"))
    from thericher_v2.execution.kis_market_data import load_kis_paper_market_data_config
    from thericher_v2.execution.kis_paper_data_capture import CaptureReadiness
    from thericher_v2.execution.paper_peer_visit import process_start
    from thericher_v2.ops.h3_dec3_target_owner import run_dec3_target_owner

    _load("peer_math", pinned["pinned/peer_math.py"])
    features = _load("dec3_pinned_features", pinned["pinned/half_inference.py"])
    parser = _load("dec3_pinned_contract", pinned["pinned/contract.py"])
    run_root, run, target = dec3_plan(source, source_pin, prebound_at)
    born = process_start(os.getpid())
    usage = shutil.disk_usage(DEC3_MARKET.anchor)
    if (
        not DEC3_OPENS <= clock() < DEC3_LAST_START
        or not born
        or usage.free * 100 < 15 * usage.total
        or re.fullmatch("[0-9a-f]{64}", target_digest) is None
        or prebound_at.utcoffset() != UTC.utcoffset(None)
        or prebound_at >= DEC3_OPENS
    ):
        raise ValueError("dec3_owner_admission")
    run_root.mkdir(exist_ok=False)
    attempt_root = run_root / "owner"
    attempt = attempt_root / "ATTEMPT.json"
    claim_digest = None

    def held():
        nonlocal claim_digest
        if not _plain(attempt) or attempt.stat().st_size > 16_384:
            return False
        raw = attempt.read_bytes()
        digest = _sha(raw)
        if claim_digest is None:
            claim = json.loads(raw)
            if (
                claim["schema"] != "H3_DEC3_DATA_ATTEMPT_V1"
                or claim["pid"] != os.getpid()
                or claim["source_sha256"] != source_pin
                or claim["launch_attempt_sha256"] != target.attempt_sha256
                or claim["owner"] != target.owner
                or claim["synthetic"] is not False
            ):
                return False
            claim_digest = digest
        return digest == claim_digest

    def ready():
        return CaptureReadiness(
            DEC3_OPENS <= clock() < DEC3_CAPTURE_END
            and process_start(os.getpid()) == born
            and held()
            and _sha((source / "SOURCE.json").read_bytes()) == source_pin
        )

    def settings():
        if not ready().ready:
            raise ValueError("dec3_owner_admission")
        return load_kis_paper_market_data_config(DOTENV, environment={})

    result = run_dec3_target_owner(
        run,
        attempt_root=attempt_root,
        target_pins=target,
        prebind_sha256=target_digest,
        clock=clock,
        owner_ready=ready,
        config_loader=settings,
        prefix_features=features.prefix_features,
        parse_input=parser.parse_input,
    )
    closed = clock()
    if (
        not DEC3_OPENS <= closed < DEC3_HARD_STOP
        or process_start(os.getpid()) != born
        or not held()
    ):
        raise ValueError("dec3_owner_close")
    _write(
        run_root / "OWNER-CLOSED.json",
        dict(
            schema="H3_DEC3_OWNER_CLOSED_V1",
            source_sha256=source_pin,
            attempt_sha256=claim_digest,
            native_start=born,
            closed_at=closed.isoformat(),
            ready_sha256=result.ready_sha256,
            target_status=result.target_status,
            target_custody_sha256=result.target_custody_sha256,
        ),
    )


def _closed_sync_data(pid, birth, digest, *, probe):
    # The frozen Data program executes the capture synchronously. Use the PID
    # in its receipt, not the Scheduler action PID (which may be a venv stub).
    # The point core separately checks the bound output bytes; this is not OS
    # proof of the launch's origin or absence of every possible host writer.
    if (
        type(pid) is not int
        or pid <= 0
        or not re.fullmatch(r"win-filetime:[1-9][0-9]{0,19}", birth)
        or not re.fullmatch(r"[a-f0-9]{64}", digest)
    ):
        return False
    receipt = DEC3_SOURCE.parent / "run" / "OWNER-CLOSED.json"
    if not _plain(receipt) or receipt.stat().st_size > 16_384:
        return False
    raw = receipt.read_bytes()
    if _sha(raw) != digest:
        return False
    observed = probe(pid)
    # Be conservative about PID reuse; denied probes raise, never return None.
    return observed is None and _plain(receipt) and receipt.read_bytes() == raw


def run_point_owner(source, source_pin, *, clock):
    if not POINT_OPENS <= clock() < POINT_LAST_START:
        raise ValueError("dec4_point_owner_clock")
    verify_source(source, source_pin, point=True)
    sys.path.insert(0, str(source / "src"))
    from thericher_v2.execution.paper_peer_visit import process_start
    from thericher_v2.ops.h3_dec4_point_owner import DATA_SOURCE_SHA256, run_dec4_point_owner

    # Verify the complete original Data source, not merely the closure receipt.
    verify_source(DEC3_SOURCE, DATA_SOURCE_SHA256, dec3=True)
    born = process_start(os.getpid())
    if born is None or not born.startswith("win-filetime:"):
        raise ValueError("dec4_point_owner_process")

    def ready():
        return (
            process_start(os.getpid()) == born
            and _sha((source / "SOURCE.json").read_bytes()) == source_pin
        )

    run_dec4_point_owner(
        point_source_sha256=source_pin,
        owner_ready=ready,
        data_owner_closed=lambda pid, birth, digest: _closed_sync_data(
            pid, birth, digest, probe=process_start
        ),
        clock=clock,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-sha256", required=True)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--nov30-forecast", action="store_true")
    modes.add_argument("--dec3-capture", action="store_true")
    modes.add_argument("--dec4-point", action="store_true")
    parser.add_argument("--target-prebind-sha256")
    parser.add_argument("--prebound-at")
    args = parser.parse_args()
    source = (
        POINT_SOURCE
        if args.dec4_point
        else DEC3_SOURCE
        if args.dec3_capture
        else FORECAST_SOURCE
        if args.nov30_forecast
        else SOURCE
    )
    if (
        Path(__file__).resolve() != (source / "scripts/run_h3_nov27_data_owner.py")
        or Path(sys.executable).resolve() != (VENV / "Scripts/pythonw.exe").resolve()
        or not (sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode)
    ):
        return 20
    sys.path.append(str(VENV / "Lib/site-packages"))
    try:
        if args.dec4_point:
            run_point_owner(source, args.source_sha256, clock=lambda: datetime.now(UTC))
        elif args.dec3_capture:
            run_dec3(
                source,
                args.source_sha256,
                clock=lambda: datetime.now(UTC),
                prebound_at=datetime.fromisoformat(args.prebound_at),
                target_digest=args.target_prebind_sha256,
            )
        else:
            driver = run_forecast if args.nov30_forecast else run_owner
            driver(source, args.source_sha256, clock=lambda: datetime.now(UTC))
    except Exception:
        return 20
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

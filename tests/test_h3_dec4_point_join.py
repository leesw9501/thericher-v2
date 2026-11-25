import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from thericher_v2.ops import h3_dec4_point_join as join
from thericher_v2.ops import h3_dec4_point_owner as owner
from thericher_v2.ops.h3_dec4_watchdog import HostJobResult

SOURCE = "f" * 64


def _yes(*args):
    return True


def _write(path, **record):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(owner._json(record))
    return owner._sha(path.read_bytes())


def _publish(root, now, source=SOURCE):
    # Invent payloads; use the production owner's exact receipt and attempt formats.
    refs = {
        key: _write(root / relpath, fixture=key)
        for key, relpath in join._LINKS.items()
        if key != "attempt_sha256"
    }
    refs["attempt_sha256"] = _write(
        root / "POINT-ATTEMPT.json",
        schema="H3_DEC4_POINT_ATTEMPT_V1",
        source_sha256=source,
        started_at=now.isoformat(),
    )
    _write(
        root / "point/OWNER-CLOSED.json",
        schema="H3_DEC4_POINT_OWNER_CLOSED_V1",
        source_sha256=source,
        source72_sha256=owner.SOURCE72_SHA256,
        data_source_sha256=owner.DATA_SOURCE_SHA256,
        closed_at=now.isoformat(),
        financial_authority=False,
        **refs,
    )
    return refs["point_sha256"]


def _options(tmp_path):
    return dict(
        argv=(sys._base_executable, "-I"),
        cwd=tmp_path,
        control=tmp_path / "control",
        point_source_sha256=SOURCE,
        owner_ready=_yes,
    )


@pytest.fixture
def attempt(tmp_path, monkeypatch):
    opts = _options(tmp_path)
    opts["control"].mkdir()
    root = tmp_path / "data/run"
    monkeypatch.setattr(owner, "_DATA", root.parent)
    monkeypatch.setenv("SystemRoot", r"C:\Windows")
    wall = [owner.OPENS, owner.OPENS + timedelta(seconds=1)]
    ticks = [100.0]
    launched = []
    birth = "win-filetime:" + str(owner._ticks(owner.OPENS + timedelta(milliseconds=500)))
    monkeypatch.setattr(join, "_now", lambda: wall[0])
    monkeypatch.setattr(join, "_monotonic", lambda: ticks[0])
    monkeypatch.setattr(join, "process_start", lambda pid: birth)
    monkeypatch.setattr(owner, "run_dec4_point_owner", lambda **kw: _publish(root, wall[0]))

    def host(argv, *, env, cwd, deadline):
        launched.append(argv)
        assert env == {"SystemRoot": r"C:\Windows"} and cwd == opts["cwd"]
        assert deadline == 100.0 + (owner.HARD_STOP - owner.OPENS).total_seconds()
        wall[0] = wall[1]
        join.run_supervised_point_child(
            control=opts["control"],
            point_source_sha256=SOURCE,
            launch_sha256=argv[-1],
            owner_ready=_yes,
            data_owner_closed=_yes,
        )
        return HostJobResult(os.getpid(), birth, 0, "EXITED")

    monkeypatch.setattr(join, "supervise_host", host)
    return opts, root, host, wall, ticks, launched


def _read(opts, digest):
    return join.read_supervised_point(
        control=opts["control"], point_source_sha256=SOURCE, completion_sha256=digest
    )


def test_join_only_once_and_rechecks_current_receipts(attempt):
    opts, root, _, _, _, launched = attempt
    digest = join.supervise_dec4_point(**opts)
    assert _read(opts, digest) == owner._sha((root / "point/OWNER-CLOSED.json").read_bytes())
    with pytest.raises(FileExistsError):
        join.supervise_dec4_point(**opts)
    assert len(launched) == 1
    (root / "input/DATA-READY.json").write_bytes(b"changed")
    with pytest.raises(ValueError, match="source_member_digest"):
        _read(opts, digest)


@pytest.mark.parametrize("seconds", [-1, 300, 780])
def test_no_launch_outside_start_window(attempt, seconds):
    opts, _, _, wall, _, launched = attempt
    wall[0] = owner.OPENS + timedelta(seconds=seconds)
    with pytest.raises(ValueError, match="clock"):
        join.supervise_dec4_point(**opts)
    assert not launched and not list(opts["control"].iterdir())


@pytest.mark.parametrize(
    "fault",
    [
        "pid",
        "birth",
        "source",
        "launch",
        "return",
        "point",
        "pending",
        "exit",
        "deadline",
        "members",
        "wall",
        "monotonic",
        "rollback",
        "unknown",
    ],
)
def test_withhold_after_attempt_even_with_owner_output(attempt, monkeypatch, fault):
    opts, root, host, wall, ticks, launched = attempt
    control = opts["control"]

    def altered(*args, **kwargs):
        proof = host(*args, **kwargs)
        if fault == "pid":
            return HostJobResult(proof.pid + 1, proof.native_start, 0, "EXITED")
        if fault == "birth":
            return HostJobResult(proof.pid, proof.native_start + "0", 0, "EXITED")
        if fault == "exit":
            return HostJobResult(proof.pid, proof.native_start, 17, "EXITED")
        if fault in ("deadline", "members"):
            status = "DEADLINE" if fault == "deadline" else "EXITED_WITH_MEMBERS"
            return HostJobResult(proof.pid, proof.native_start, 0, status)
        if fault == "wall":
            wall[0] = owner.HARD_STOP
        elif fault == "monotonic":
            ticks[0] = kwargs["deadline"]
        elif fault == "rollback":
            wall[0] = owner.OPENS
        elif fault == "unknown":
            raise TimeoutError("job_join_unproven")
        elif fault == "pending":
            (root / "point/OWNER-CLOSED.pending").touch()
        elif fault == "return":
            (control / join._RETURN).unlink()
        else:
            path = {
                "source": root / "point/OWNER-CLOSED.json",
                "launch": control / join._LAUNCH,
                "point": root / "point/POINT.json",
            }[fault]
            path.write_bytes(
                path.read_bytes().replace(SOURCE.encode(), b"a" * 64)
                if fault == "source"
                else b"{}"
            )
        return proof

    monkeypatch.setattr(join, "supervise_host", altered)
    with pytest.raises((ValueError, FileExistsError, OSError)):
        join.supervise_dec4_point(**opts)
    assert not (control / join._COMPLETE).exists()
    assert (root / "point/POINT.json").exists()
    assert (control / join._LAUNCH).exists()
    wall[0], ticks[0] = owner.OPENS, 100.0
    with pytest.raises(FileExistsError):
        join.supervise_dec4_point(**opts)
    assert len(launched) == 1


def test_preexisting_bare_owner_record_is_not_a_launch_or_completion(attempt):
    opts, root, _, _, _, launched = attempt
    _publish(root, owner.OPENS)
    with pytest.raises(FileExistsError):
        join.supervise_dec4_point(**opts)
    with pytest.raises(FileNotFoundError):
        _read(opts, owner._sha((root / "point/OWNER-CLOSED.json").read_bytes()))
    assert not launched


def test_reentry_cannot_launch_after_claim(attempt, monkeypatch):
    opts, _, host, _, _, launched = attempt

    def reentered(*args, **kwargs):
        with pytest.raises(FileExistsError):
            join.supervise_dec4_point(**opts)
        return host(*args, **kwargs)

    monkeypatch.setattr(join, "supervise_host", reentered)
    join.supervise_dec4_point(**opts)
    assert len(launched) == 1


@pytest.mark.parametrize("fault", ["late", "replace"])
def test_staged_receipt_is_not_completion(attempt, monkeypatch, fault):
    opts, root, _, wall, _, _ = attempt
    write_once = owner._write_once

    def staged(path, raw):
        write_once(path, raw)
        if path.name == join._PENDING:
            if fault == "late":
                wall[0] = owner.HARD_STOP
            else:
                point = root / "point/POINT.json"
                replacement = point.with_suffix(".replacement")
                replacement.write_bytes(point.read_bytes())
                replacement.replace(point)

    monkeypatch.setattr(owner, "_write_once", staged)
    with pytest.raises(ValueError, match="clock|changed"):
        join.supervise_dec4_point(**opts)
    control = opts["control"]
    assert not (control / join._COMPLETE).exists()
    with pytest.raises(FileExistsError):
        _read(opts, owner._sha((control / join._PENDING).read_bytes()))


@pytest.mark.skipif(os.name != "nt", reason="native Windows Job and FILETIME")
@pytest.mark.parametrize("retain_member", [False, True])
def test_native_root_and_empty_job_are_required(tmp_path, monkeypatch, retain_member):
    opts = _options(tmp_path)
    opts["control"].mkdir()
    root = tmp_path / "data"
    start = datetime.now(UTC) - timedelta(seconds=1)
    monkeypatch.setattr(owner, "OPENS", start)
    monkeypatch.setattr(owner, "LAST_START", start + timedelta(seconds=30))
    monkeypatch.setattr(owner, "HARD_STOP", start + timedelta(seconds=40))
    monkeypatch.setattr(owner, "_DATA", root)
    script = """
import runpy, subprocess, sys
from datetime import datetime
from pathlib import Path
sys.path[:0] = sys.argv[1:4]
fixture = runpy.run_path(sys.argv[4])
join, owner = fixture["join"], fixture["owner"]
owner._DATA = Path(sys.argv[5])
owner.OPENS, owner.LAST_START, owner.HARD_STOP = map(datetime.fromisoformat, sys.argv[6:9])
owner.run_dec4_point_owner = lambda **kw: fixture["_publish"](owner._DATA / "run", join._now())
join.run_supervised_point_child(
    control=Path(sys.argv[10]), point_source_sha256=fixture["SOURCE"], launch_sha256=sys.argv[11],
    owner_ready=fixture["_yes"], data_owner_closed=fixture["_yes"],
)
if sys.argv[9] == "True":
    subprocess.Popen([sys.executable, "-I", "-c", "import time; time.sleep(30)"])
"""
    opts["argv"] += (
        "-c",
        script,
        str(Path(__file__).resolve().parents[1] / "src"),
        str(Path(pytest.__file__).resolve().parents[1]),
        str(Path(__file__).resolve().parent),
        str(Path(__file__).resolve()),
        str(root),
        start.isoformat(),
        owner.LAST_START.isoformat(),
        owner.HARD_STOP.isoformat(),
        str(retain_member),
        str(opts["control"]),
    )
    if retain_member:
        with pytest.raises(ValueError, match="unproven"):
            join.supervise_dec4_point(**opts)
        assert not (opts["control"] / join._COMPLETE).exists()
    else:
        assert _read(opts, join.supervise_dec4_point(**opts)) == owner._sha(
            (root / "run/point/OWNER-CLOSED.json").read_bytes()
        )
    assert (opts["control"] / join._RETURN).exists()

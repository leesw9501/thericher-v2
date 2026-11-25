"""Own the dated, public-side Dec4 proposal; never acquire broker authority."""

import hashlib
import json
import os
import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType

from thericher_v2.data.kis_paper_h3_capture import _is_utc, _read_native
from thericher_v2.data.kis_paper_h3_producer import (
    CAPTURE_CLOSES_UTC,
    CAPTURE_OPENS_UTC,
    INPUT_HARD_STOP_UTC,
)
from thericher_v2.execution.kis_paper_data_capture import _safe_path
from thericher_v2.execution.paper_peer_visit import process_start
from thericher_v2.models.h3_shadow_point import (
    MODEL_SHA,
    STATS_SHA,
    WEIGHTS_SHA,
    read_dec4_h3_shadow_point,
)
from thericher_v2.ops.h3_dec4_run import Dec4H3Run, run_dec4_point

OPENS = datetime(2026, 12, 3, 21, 47, tzinfo=UTC)
LAST_START = OPENS.replace(minute=52)
HARD_STOP = OPENS.replace(hour=22, minute=0)
DATA_NAME = "h3-dec3-modp1-owner-20261203-v1"
DATA_SOURCE_SHA256 = "878615272a71b035f61438d3242163c50f548350842409e6bc64dd6415b861bf"
SOURCE72_SHA256 = "72eb95e32abfdc96bb7e72c1628177a51633fbf5da74c74be5f77d35bcdbd4d5"
_RESEARCH = Path("D:/thericher-v2/model-artifacts/research")
_DATA = _RESEARCH.parent / "data" / DATA_NAME
_MARKET = Path("D:/market_data/us_equities/kis_paper_private") / DATA_NAME
_SOURCE72 = "current-nov9-lstm-h3-clock-bound-publisher-20261106-v1"
_PREBIND = "40e4ae04030c4aa855d6434ff694beedf7cd2761b54d6599eefc360a8a7baf27"
_PARSER = "pinned/contract.py"
_PARSER_SHA = "075e9c5ddf495ef9e59d83d08f298ab840e0507b8a92d626387a902d33da003e"
_WRITER = "scripts/run_h3_nov27_data_owner.py"
_WRITER_SHA = "bdc42ce518780b8b83ac217803fe75c972ece93c89559572706132ad532eeafb"
_MEMBERS = (
    ("models.py", MODEL_SHA, 1567),
    ("model/STATS.npz", STATS_SHA, 1271),
    ("model/BEST.safetensors", WEIGHTS_SHA, 29828),
)
_READY_KEYS = {
    "schema",
    "source_sha256",
    "synthetic",
    "decision_at",
    "closed_at",
    "capture_state_sha256",
    "input_header_sha256",
    "input_payload_sha256",
    "ready_at",
}


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _digest(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _json(document):
    return json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False).encode(
        "ascii"
    )


def _record(raw, keys):
    document = json.loads(raw)
    if type(document) is not dict or document.keys() != keys or _json(document) != raw:
        raise ValueError("dec4_owner_record")
    return document


def _read(path, limit=16_384):
    if not path.is_absolute() or _safe_path(path) != path or path.lstat().st_size > limit:
        raise ValueError("dec4_owner_member")
    raw = _read_native(path.parent, str(path))
    if len(raw) > limit:
        raise ValueError("dec4_owner_member")
    return raw


def _pinned(path, digest, limit):
    raw = _read(path, limit)
    if _sha(raw) != digest:
        raise ValueError("dec4_owner_source_member_digest")
    return raw


def _absent(path):
    try:
        path.lstat()
    except FileNotFoundError:
        return
    raise FileExistsError("dec4_owner_pending_or_consumed")


def _stamp(value):
    if type(value) is not str:
        raise ValueError("dec4_data_clock")
    stamp = datetime.fromisoformat(value)
    if not _is_utc(stamp) or stamp.isoformat() != value:
        raise ValueError("dec4_data_clock")
    return stamp


def _ticks(at):
    delta = at - datetime(1601, 1, 1, tzinfo=UTC)
    return (delta.days * 86_400 + delta.seconds) * 10_000_000 + delta.microseconds * 10


def _birth(value):
    if type(value) is not str or re.fullmatch(r"win-filetime:[1-9][0-9]{0,18}", value) is None:
        raise ValueError("dec4_data_native_start")
    return int(value.split(":")[1])


def _read_data(run, binding, data_owner_closed):
    source = json.loads(_pinned(_DATA / "source/SOURCE.json", DATA_SOURCE_SHA256, 1024 * 1024))
    if (
        source["schema"] != "H3_DEC3_DATA_SOURCE_V1"
        or source["run"] != DATA_NAME
        or source["files"].get(_WRITER) != _WRITER_SHA
        or source["files"].get(_PARSER) != _PARSER_SHA
    ):
        raise ValueError("dec4_data_source")

    root = run.input_root.parent
    attempt_root = root / "owner"
    for path in (
        root / "FAILED.json",
        *(
            run.input_root / p
            for p in (
                "READY.pending",
                "DATA-READY.pending",
            )
        ),
    ):
        _absent(path)
    attempt = _read(attempt_root / "ATTEMPT.json")
    owner = _read(root / "OWNER-CLOSED.json")
    a = _record(
        attempt,
        {
            "schema",
            "owner",
            "launch_attempt_sha256",
            "source_sha256",
            "target_prebind_sha256",
            "started_at",
            "pid",
            "synthetic",
            "roots",
        },
    )
    c = _record(
        owner,
        {
            "schema",
            "source_sha256",
            "attempt_sha256",
            "native_start",
            "closed_at",
            "ready_sha256",
            "target_status",
            "target_custody_sha256",
        },
    )
    if (
        a["schema"] != "H3_DEC3_DATA_ATTEMPT_V1"
        or a["owner"] != "thericher-" + DATA_NAME
        or a["launch_attempt_sha256"] != _sha(f"{DATA_NAME}:{DATA_SOURCE_SHA256}".encode("ascii"))
        or a["source_sha256"] != DATA_SOURCE_SHA256
        or a["synthetic"] is not False
        or type(a["pid"]) is not int
        or not 0 < a["pid"] < 2**32
        or a["roots"]
        != [
            str(path)
            for path in (
                run.market_root,
                run.artifact_root,
                run.input_root,
                run.point_root,
                attempt_root,
            )
        ]
        or c["schema"] != "H3_DEC3_OWNER_CLOSED_V1"
        or c["source_sha256"] != DATA_SOURCE_SHA256
        or c["attempt_sha256"] != _sha(attempt)
        or not _digest(c["ready_sha256"])
    ):
        raise ValueError("dec4_data_owner_binding")
    status = c["target_status"]
    prebind, custody = a["target_prebind_sha256"], c["target_custody_sha256"]
    if not (
        (status == "not_bound" and prebind is None and custody is None)
        or (status in ("seal_failed", "pin_failed") and prebind == _PREBIND and custody is None)
        or (status == "pinned" and prebind == _PREBIND and _digest(custody))
    ):
        raise ValueError("dec4_target_categorical_metadata")

    ready_digest = c["ready_sha256"]
    ready_raw = _read(run.input_root / "READY.json")
    data_ready = _read(run.input_root / "DATA-READY.json")
    if _sha(ready_raw) != ready_digest or data_ready != run._receipt(ready_digest):
        raise ValueError("dec4_data_ready_digest")
    ready = _record(ready_raw, _READY_KEYS)
    if (
        ready["schema"] != "H3_PUBLISHER_INPUT_READY_V1"
        or ready["source_sha256"] != DATA_SOURCE_SHA256
        or ready["synthetic"] is not False
        or ready["decision_at"] != binding.decision_at.isoformat()
        or not all(
            _digest(ready[key])
            for key in (
                "capture_state_sha256",
                "input_header_sha256",
                "input_payload_sha256",
            )
        )
    ):
        raise ValueError("dec4_data_ready_binding")
    started, closed = _stamp(a["started_at"]), _stamp(c["closed_at"])
    capture_closed, ready_at = _stamp(ready["closed_at"]), _stamp(ready["ready_at"])
    born = _birth(c["native_start"])
    if not (
        CAPTURE_OPENS_UTC <= started < CAPTURE_CLOSES_UTC
        and started <= capture_closed < CAPTURE_CLOSES_UTC
        and capture_closed <= ready_at <= closed < INPUT_HARD_STOP_UTC
        and _ticks(CAPTURE_OPENS_UTC) <= born <= _ticks(started)
    ):
        raise ValueError("dec4_data_clock")
    observed = process_start(a["pid"])
    if (observed is not None and _birth(observed) <= born) or data_owner_closed(
        a["pid"], c["native_start"], _sha(owner)
    ) is not True:
        raise ValueError("dec4_data_process_not_closed")
    return _sha(attempt), _sha(owner), ready_digest, _sha(data_ready)


def _checkpoint():
    source = json.loads(
        _pinned(_RESEARCH / _SOURCE72 / "SOURCE.json", SOURCE72_SHA256, 1024 * 1024)
    )
    if source["schema"] != "NOV9_LSTM_H3_CLOCK_BOUND_SOURCE_V2":
        raise ValueError("dec4_owner_source72_schema")
    retained = []
    for member, digest, size in _MEMBERS:
        pin = source["mount_files"]["/" + member]
        path = Path(pin["path"])
        if (
            pin["sha256"] != digest
            or not path.is_relative_to(_RESEARCH)
            or {"path": path.as_posix(), "sha256": digest, "bytes": size} not in source["pins"]
        ):
            raise ValueError("dec4_owner_source72_member")
        raw = _pinned(path, digest, size)
        if len(raw) != size:
            raise ValueError("dec4_owner_source72_size")
        retained.append(raw)
    return retained


def _write_once(path, raw):
    if _safe_path(path) != path:
        raise ValueError("dec4_owner_output_path")
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    if _read(path) != raw:
        raise ValueError("dec4_owner_output_changed")


def run_dec4_point_owner(
    *,
    point_source_sha256: str,
    owner_ready: Callable[[], bool],
    data_owner_closed: Callable[[int, str, str], bool],
    clock: Callable[[], datetime],
) -> str:
    """Return the point digest only after exact point and closure readback.

    The launcher must attest the pinned current source/ACLs and current owner,
    and positively attest the original Dec3 process tree is closed for the
    given PID, birth and receipt digest. A PID probe alone is not tree proof.
    The launcher owns hard process termination at HARD_STOP; this core checks
    wall time and denies late results but cannot interrupt native execution.
    Consumers must require successful launcher closure before HARD_STOP and
    point/OWNER-CLOSED.json with the matching digest, not a bare POINT.json.
    """
    if not _digest(point_source_sha256):
        raise ValueError("dec4_owner_source")
    last = OPENS

    def guarded_clock():
        nonlocal last
        now = clock()
        if not _is_utc(now) or not last <= now < HARD_STOP:
            raise ValueError("dec4_owner_clock")
        if owner_ready() is not True:
            raise ValueError("dec4_owner_not_ready")
        last = now
        return now

    def within_start():
        now = guarded_clock()
        if now >= LAST_START:
            raise ValueError("dec4_owner_start")
        return now

    started = within_start()
    root = _DATA / "run"
    run = Dec4H3Run(
        _MARKET, root / "capture", root / "input", root / "point", DATA_SOURCE_SHA256, False
    )
    binding = run._preflight(data=False)
    claim = root / "POINT-ATTEMPT.json"
    claim_raw = _json(
        dict(
            schema="H3_DEC4_POINT_ATTEMPT_V1",
            source_sha256=point_source_sha256,
            started_at=started.isoformat(),
        )
    )
    within_start()
    _write_once(claim, claim_raw)
    refs = _read_data(run, binding, data_owner_closed)
    parser_raw = _pinned(_DATA / "source" / _PARSER, _PARSER_SHA, 16_384)
    model_source, stats, weights = _checkpoint()
    within_start()
    parser = ModuleType("dec4_pinned_input_contract")
    exec(compile(parser_raw, "<pinned Dec3 input contract>", "exec"), vars(parser))

    def recheck():
        if _read(claim) != claim_raw or _read_data(run, binding, data_owner_closed) != refs:
            raise ValueError("dec4_owner_handoff_changed")

    def validate_input(*args, **kwargs):
        parser.validate_input(*args, **kwargs)
        recheck()
        within_start()

    recheck()
    within_start()
    digest = run_dec4_point(
        run,
        clock=guarded_clock,
        owner_ready=owner_ready,
        validate_input=validate_input,
        model_source=model_source,
        stats=stats,
        weights=weights,
    )
    read_dec4_h3_shadow_point(
        run.point_root, binding=binding, ready_sha256=refs[2], point_sha256=digest
    )
    recheck()
    pending, final = (
        run.point_root / name
        for name in (
            "OWNER-CLOSED.pending",
            "OWNER-CLOSED.json",
        )
    )
    raw = _json(
        dict(
            schema="H3_DEC4_POINT_OWNER_CLOSED_V1",
            source_sha256=point_source_sha256,
            source72_sha256=SOURCE72_SHA256,
            data_source_sha256=DATA_SOURCE_SHA256,
            data_attempt_sha256=refs[0],
            data_owner_sha256=refs[1],
            ready_sha256=refs[2],
            data_ready_sha256=refs[3],
            attempt_sha256=_sha(claim_raw),
            point_sha256=digest,
            closed_at=guarded_clock().isoformat(),
            financial_authority=False,
        )
    )
    _write_once(pending, raw)
    _absent(final)
    guarded_clock()
    pending.rename(final)
    try:
        if _read(final) != raw:
            raise ValueError("dec4_owner_close_changed")
        guarded_clock()
    except Exception:
        final.unlink()
        raise
    return digest

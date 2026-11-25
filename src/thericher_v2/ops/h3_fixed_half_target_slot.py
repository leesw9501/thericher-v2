"""Read the prebound Nov30-Dec3 fixed-half slot at block end, without scoring."""

from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path

from thericher_v2.data.kis_paper_h3_capture import _is_utc, _read_native
from thericher_v2.data.kis_paper_h3_daily_panel import (
    NET25_H3_AXIS,
    H3DailyPanelPlan,
    qualify_h3_daily_panel,
)
from thericher_v2.data.kis_paper_h3_producer import (
    CAPTURE_CLOSES_UTC,
    CAPTURE_OPENS_UTC,
    INPUT_HARD_STOP_UTC,
)
from thericher_v2.execution.kis_paper_data_capture import CaptureResult, _safe_path
from thericher_v2.research.prospective_h3_calendar import H3Interval
from thericher_v2.research.prospective_h3_marks import (
    ProspectiveH3Marks,
    project_prospective_h3_marks,
)
from thericher_v2.research.prospective_h3_target_custody import (
    Nov30H3TargetPins,
    _digest,
    _document,
    _json,
    _sha,
    _stamp,
    read_nov30_h3_target_custody,
)

INTERVAL = H3Interval(date(2026, 11, 30), date(2026, 12, 3))
RELEASE_AT = datetime(2026, 12, 28, 21, tzinfo=UTC)
_DATA_NAME = "h3-dec3-modp1-owner-20261203-v1"
_ARTIFACTS = Path("D:/thericher-v2/model-artifacts")
_DATA = _ARTIFACTS / "data" / _DATA_NAME
_MARKET = Path("D:/market_data/us_equities/kis_paper_private") / _DATA_NAME
_SOURCE = "878615272a71b035f61438d3242163c50f548350842409e6bc64dd6415b861bf"
_PREBIND_FILE = "bc74279cbe725a644c8a7fb7387136563e73f7d9204ed58898fed853c345b40b"
_PREBIND = "40e4ae04030c4aa855d6434ff694beedf7cd2761b54d6599eefc360a8a7baf27"
_PREBOUND_AT = datetime(2026, 11, 25, 19, 3, 26, tzinfo=UTC)
_FORECAST = _ARTIFACTS / "research/h3-nov30-fixed-half-forecast-20261130-v1/run"
_FORECAST_SOURCE = "f37981f4d4cd232be6f5382749fd5c50a14195e93e87f535d6286aec57244a44"
_FORECAST_OPENS = datetime(2026, 11, 30, 14, 12, tzinfo=UTC)
_FORECAST_CUTOFF = _FORECAST_OPENS.replace(minute=25)
_MAX_NATIVE = 1024 * 1024


def _pins():
    root = _DATA / "run"
    return Nov30H3TargetPins(
        owner="thericher-" + _DATA_NAME,
        source_sha256=_SOURCE,
        attempt_sha256=_sha(f"{_DATA_NAME}:{_SOURCE}".encode("ascii")),
        market_root=_MARKET,
        artifact_root=root / "capture",
        target_root=root / "target",
        prebound_at=_PREBOUND_AT,
        release_at=RELEASE_AT,
        synthetic=False,
    )


def _record(raw, keys):
    doc = _document(raw)
    if doc.keys() != keys or _json(doc) != raw:
        raise ValueError("h3_target_slot_record")
    return doc


def _fingerprint(path, limit):
    if not path.is_absolute() or _safe_path(path) != path:
        raise ValueError("h3_target_slot_path")
    info = path.lstat()
    if not 0 < info.st_size <= limit:
        raise ValueError("h3_target_slot_size")
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def _ticks(stamp):
    delta = stamp - datetime(1601, 1, 1, tzinfo=UTC)
    return (delta.days * 86400 + delta.seconds) * 10_000_000 + delta.microseconds * 10


def read_nov30_fixed_half_target_slot(
    *,
    data_owner_sha256: str,
    forecast_owner_sha256: str,
    reader_ready: Callable[[], bool],
    clock: Callable[[], datetime],
) -> ProspectiveH3Marks:
    """Return only the first frozen slot's exact OPEN4/CLOSE3 marks.

    The block launcher supplies independently retained successful closure
    digests (not self-pins from these paths). Its probe attests the frozen
    reader source, one-shot authority, RO isolation and positive owner-tree
    closure for both digests, with no active/unknown writer to these roots.
    It owns any outer deadline and verifies forecast seal admission separately.
    This core does not read forecast scores, raw wire bodies or feature files.
    Failure withholds the slot; it never retries or substitutes another edition.
    """
    if not all(_digest(x) for x in (data_owner_sha256, forecast_owner_sha256)):
        raise ValueError("h3_target_slot_owner_digest")
    last = RELEASE_AT
    observed = {}

    def gate():
        nonlocal last
        now = clock()
        if not _is_utc(now) or now < last or reader_ready() is not True:
            raise ValueError("h3_target_slot_read_denied")
        last = now
        return now

    def track(path, limit):
        gate()
        fingerprint = _fingerprint(path, limit)
        if observed.setdefault(path, (limit, fingerprint)) != (limit, fingerprint):
            raise ValueError("h3_target_slot_member_changed")

    def read(path, *, digest=None, limit=16_384):
        track(path, limit)
        raw = _read_native(path.parent, str(path))
        track(path, limit)
        if len(raw) > limit or (digest is not None and _sha(raw) != digest):
            raise ValueError("h3_target_slot_member_digest")
        return raw

    gate()
    pins = _pins()
    root = _DATA / "run"
    attempt_root = root / "owner"
    forecast = _record(
        read(_FORECAST / "OWNER-CLOSED.json", digest=forecast_owner_sha256),
        {"schema", "source", "data_owner_sha256", "ready_sha256", "seal_sha256", "closed_at"},
    )
    if (
        forecast["schema"] != "H3_NOV30_FORECAST_OWNER_CLOSED_V1"
        or forecast["source"] != _FORECAST_SOURCE
        or not all(
            _digest(forecast[k]) for k in ("data_owner_sha256", "ready_sha256", "seal_sha256")
        )
        or not _FORECAST_OPENS <= _stamp(forecast["closed_at"]) < _FORECAST_CUTOFF
    ):
        raise ValueError("h3_target_slot_forecast")

    read(_DATA / "source/SOURCE.json", digest=_SOURCE, limit=_MAX_NATIVE)
    if read(_DATA / "TARGET-PREBIND.json", digest=_PREBIND_FILE) != _json(
        dict(
            prebound_at=_PREBOUND_AT.isoformat(),
            source_sha256=_SOURCE,
            target_prebind_sha256=_PREBIND,
        )
    ):
        raise ValueError("h3_target_slot_prebind")
    owner = _record(
        read(root / "OWNER-CLOSED.json", digest=data_owner_sha256),
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
        owner["schema"] != "H3_DEC3_OWNER_CLOSED_V1"
        or owner["source_sha256"] != _SOURCE
        or owner["target_status"] != "pinned"
        or not all(
            _digest(owner[k]) for k in ("attempt_sha256", "ready_sha256", "target_custody_sha256")
        )
    ):
        raise ValueError("h3_target_slot_data_owner")
    attempt = _record(
        read(attempt_root / "ATTEMPT.json", digest=owner["attempt_sha256"]),
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
    started, closed = _stamp(attempt["started_at"]), _stamp(owner["closed_at"])
    born = owner["native_start"]
    head, _, ticks = born.partition(":") if type(born) is str else ("", "", "")
    if (
        attempt["schema"] != "H3_DEC3_DATA_ATTEMPT_V1"
        or attempt["owner"] != pins.owner
        or attempt["source_sha256"] != _SOURCE
        or attempt["launch_attempt_sha256"] != pins.attempt_sha256
        or attempt["target_prebind_sha256"] != _PREBIND
        or attempt["synthetic"] is not False
        or type(attempt["pid"]) is not int
        or not 0 < attempt["pid"] < 2**32
        or attempt["roots"]
        != [
            str(path)
            for path in (
                _MARKET,
                pins.artifact_root,
                root / "input",
                root / "point",
                attempt_root,
            )
        ]
        or not CAPTURE_OPENS_UTC <= started < CAPTURE_CLOSES_UTC
        or not started <= closed < INPUT_HARD_STOP_UTC
        or head != "win-filetime"
        or not (ticks.isascii() and ticks.isdecimal() and len(ticks) == 18)
        or not _ticks(CAPTURE_OPENS_UTC) <= int(ticks) <= _ticks(started)
    ):
        raise ValueError("h3_target_slot_attempt")
    gate()
    try:
        (attempt_root / "TARGET-PIN.pending").lstat()
    except FileNotFoundError:
        pass
    else:
        raise ValueError("h3_target_slot_pin_pending")
    pin = read(attempt_root / "TARGET-PIN.json")
    state_path = pins.artifact_root / "capture-state.json"
    track(pins.target_root / "TARGET-CUSTODY.json", 16_384)
    track(state_path, _MAX_NATIVE)
    custody = read_nov30_h3_target_custody(
        pins,
        prebind_sha256=_PREBIND,
        expected_sha256=owner["target_custody_sha256"],
        now=gate(),
    )
    if pin != _json(
        dict(
            schema="H3_DEC3_TARGET_PIN_V1",
            attempt_record_sha256=owner["attempt_sha256"],
            prebind_sha256=_PREBIND,
            capture_state_sha256=custody.capture_state_sha256,
            capture_closed_at=custody.capture_closed_at.isoformat(),
            target_custody_sha256=owner["target_custody_sha256"],
        )
    ):
        raise ValueError("h3_target_slot_target_pin")
    state = _document(read(state_path, digest=custody.capture_state_sha256, limit=_MAX_NATIVE))
    if (
        not started
        <= _stamp(state["started_utc"])
        <= custody.capture_closed_at
        <= (custody.sealed_at)
        <= closed
    ):
        raise ValueError("h3_target_slot_capture_clock")

    plan = H3DailyPanelPlan(NET25_H3_AXIS, INTERVAL.expiry)

    def pages():
        for query in plan.queries:
            item = state["completed"][query.key]
            ref = item["native"]
            yield (
                CaptureResult(query.key, "ACCEPTED", row_count=item["row_count"], native=ref),
                read(Path(ref["path"]), digest=ref["sha256"], limit=_MAX_NATIVE),
            )

    marks = project_prospective_h3_marks(qualify_h3_daily_panel(plan, pages()), INTERVAL)
    for path, (limit, _) in observed.items():
        track(path, limit)
    gate()
    return marks

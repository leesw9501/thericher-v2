"""Join the installed Nov27 Data owner to a dated fixed-half CPU forecast."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from thericher_v2.data.kis_paper_h3_capture import _read_native
from thericher_v2.data.kis_paper_h3_producer import (
    NOV27_CAPTURE_CLOSES_UTC,
    NOV27_CAPTURE_OPENS_UTC,
    NOV27_DECISION_UTC,
    NOV27_INPUT_HARD_STOP_UTC,
    H3ProducedInput,
)
from thericher_v2.execution.kis_paper_data_capture import _safe_path
from thericher_v2.models.h3_publisher_input import H3InputBinding
from thericher_v2.research.nov30_h3_checkpoint_loader import (
    FIT_SHA256,
    OLD60_PIN,
    SELF_PIN,
    make_nov30_h3_forward,
)
from thericher_v2.research.prospective_h3_forecast import (
    Nov30H3ForecastPins,
    _publish,
    _stage,
    seal_nov30_h3_forecast,
)

OPENS = datetime(2026, 11, 30, 14, 12, tzinfo=UTC)
LAST_START = datetime(2026, 11, 30, 14, 13, tzinfo=UTC)
HARD_STOP = NOV27_DECISION_UTC
DATA_NAME = "h3-nov27-modp1-owner-20261127-v1"
DATA_SOURCE_SHA256 = "4420f9c63ac74c480aa381ad0510eae8df5a42fd0d6f83cfa8d9724154c12f53"
_RESEARCH = Path("D:/thericher-v2/model-artifacts/research")
_SELF = _RESEARCH / "current-h3-entry-pool-self-context-development-20261107-v1"
_OLD = _RESEARCH / "current-h123-lstm-tcn-comparison-20261106-v1/run1"
_MEMBERS = dict(
    self_source=_SELF / "models.py",
    self_checkpoint=_SELF / "fit-self/BEST.safetensors",
    old60_source=_OLD / "models.py",
    old60_checkpoint=_OLD / "LSTM-fit/BEST.safetensors",
    fit=_RESEARCH / "current-net25-patch-transformer-development-20261105-v1/fit-out/STATS.npz",
    input_adapter=_SELF / "input_adapter.py",
    entry_io=_SELF / "entry_io.py",
)
_POLICY = dict(
    schema="H3_FIXED_HALF_FORWARD_BLOCK_V1",
    dates=[
        ["2026-11-30", "2026-12-03"],
        ["2026-12-04", "2026-12-09"],
        ["2026-12-10", "2026-12-15"],
        ["2026-12-16", "2026-12-21"],
        ["2026-12-22", "2026-12-28"],
    ],
    endpoint="OPEN_TO_OPEN3",
    blend=["1/2", "1/2"],
    select="strict_positive",
    nominal_per_name="0.5/17",
    fee_bp_per_leg=25,
    comparators=["funded_gross_EW17", "cash"],
    minimum_admitted=4,
    interpretation="descriptive_not_promotion",
)


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii")


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


POLICY_SHA256 = _sha(_json(_POLICY))


def _read(path):
    if path.stat().st_size > 20 * 1024 * 1024:
        raise ValueError("nov30_member_size")
    return _read_native(path.parent, str(path))


def _timestamp(value):
    stamp = datetime.fromisoformat(value)
    if stamp.utcoffset() != UTC.utcoffset(None):
        raise ValueError("nov30_data_clock")
    return stamp


def read_nov27_owner_ready(data_root, *, source_pin):
    """Join exact owned Data files; absent and partial captures cannot admit."""
    run = data_root / "run"
    if _sha(_read(data_root / "source" / "SOURCE.json")) != source_pin:
        raise ValueError("nov30_data_source")
    if (run / "FAILED.json").exists() or (run / "input" / "READY.pending").exists():
        raise ValueError("nov30_data_incomplete")
    attempt = _read(run / "ATTEMPT.json")
    owner = _read(run / "OWNER-CLOSED.json")
    a, c = json.loads(attempt), json.loads(owner)
    if (
        type(a) is not dict
        or a.keys() != {"source", "run", "started_at"}
        or a["source"] != source_pin
        or a["run"] != DATA_NAME
        or type(c) is not dict
        or c.keys()
        != {
            "schema",
            "source",
            "attempt_sha256",
            "ready_sha256",
            "closed_at",
            "read_only",
            "paper_only",
        }
        or c["schema"] != "H3_NOV27_OWNER_CLOSED_V1"
        or c["source"] != source_pin
        or c["attempt_sha256"] != _sha(attempt)
        or c["read_only"] is not True
        or c["paper_only"] is not True
        or attempt != _json(a)
        or owner != _json(c)
    ):
        raise ValueError("nov30_data_owner_binding")
    started, closed = _timestamp(a["started_at"]), _timestamp(c["closed_at"])
    if not (
        NOV27_CAPTURE_OPENS_UTC <= started < NOV27_CAPTURE_CLOSES_UTC
        and started <= closed < NOV27_INPUT_HARD_STOP_UTC
    ):
        raise ValueError("nov30_data_clock")
    input_root = run / "input"
    ready_raw = _read(input_root / "READY.json")
    if _sha(ready_raw) != c["ready_sha256"]:
        raise ValueError("nov30_data_ready_digest")
    ready = json.loads(ready_raw)
    if not (
        started <= _timestamp(ready["closed_at"]) < NOV27_CAPTURE_CLOSES_UTC
        and _timestamp(ready["closed_at"]) <= _timestamp(ready["ready_at"]) <= closed
    ):
        raise ValueError("nov30_data_ready_clock")
    binding = H3InputBinding(source_pin, NOV27_DECISION_UTC, NOV27_INPUT_HARD_STOP_UTC, False)
    return H3ProducedInput(
        input_root, run / "capture" / "capture-state.json", binding, c["ready_sha256"]
    ), _sha(owner)


def run_nov30_forecast(data_root, destination, *, forecast_pin, clock, validate_input):
    """Run one CPU forecast only if the actual prior Data owner is closed."""
    started = clock()
    if started.utcoffset() != UTC.utcoffset(None) or not OPENS <= started < LAST_START:
        raise ValueError("nov30_forecast_bad_start")
    if (
        not destination.is_absolute()
        or _safe_path(destination) != destination
        or destination.exists()
    ):
        raise ValueError("nov30_forecast_destination")
    produced, owner_ref = read_nov27_owner_ready(data_root, source_pin=DATA_SOURCE_SHA256)
    pins = Nov30H3ForecastPins(
        DATA_SOURCE_SHA256, forecast_pin, SELF_PIN, OLD60_PIN, FIT_SHA256, POLICY_SHA256
    )
    forward = make_nov30_h3_forward(**{name: _read(path) for name, path in _MEMBERS.items()})
    last = OPENS

    def limited_clock():
        nonlocal last
        now = clock()
        if now.utcoffset() != UTC.utcoffset(None) or not last <= now < HARD_STOP:
            raise ValueError("nov30_forecast_deadline")
        last = now
        return now

    digest = seal_nov30_h3_forecast(
        destination,
        produced,
        pins=pins,
        clock=limited_clock,
        validate_input=validate_input,
        forward=forward,
    )
    if read_nov27_owner_ready(data_root, source_pin=DATA_SOURCE_SHA256) != (produced, owner_ref):
        raise ValueError("nov30_data_owner_changed")
    pending = destination / "OWNER-CLOSED.pending"
    raw = _json(
        dict(
            schema="H3_NOV30_FORECAST_OWNER_CLOSED_V1",
            source=forecast_pin,
            data_owner_sha256=owner_ref,
            ready_sha256=produced.ready_sha256,
            seal_sha256=digest,
            closed_at=limited_clock().isoformat(),
        )
    )
    _stage(pending, raw)
    limited_clock()
    final = destination / "OWNER-CLOSED.json"
    _publish(pending, final)
    try:
        limited_clock()
    except ValueError:
        final.unlink()
        raise
    return digest

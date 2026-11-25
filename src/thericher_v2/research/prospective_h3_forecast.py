"""Input-only, one-attempt fixed-half forecast for the Nov30 research slot."""

import hashlib
import json
import math
import os
import re
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import MappingProxyType

import numpy as np

from thericher_v2.data.kis_paper_h3_capture import _read_native
from thericher_v2.data.kis_paper_h3_producer import (
    NOV27_CAPTURE_OPENS_UTC,
    NOV27_DECISION_UTC,
    NOV27_INPUT_HARD_STOP_UTC,
    H3ProducedInput,
)
from thericher_v2.execution.kis_paper_data_capture import _safe_path
from thericher_v2.models.h3_publisher_input import H3InputBinding, read_h3_publisher_input

_CLOSE = datetime(2026, 11, 27, 18, tzinfo=UTC)
_ENTRY = datetime(2026, 11, 30, 14, 30, tzinfo=UTC)
_EXPIRY = datetime(2026, 12, 3, 14, 30, tzinfo=UTC)
_ROLE = "FUTURE_20261127_ASOF_20261130"
_KEYS = tuple(f"20261130|{i:02d}" for i in range(17))
_FIELDS = {"x", "z", "key", "known", "entry_index", "context_close", "decision_at"}


def _require_digest(value):
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("h3_forecast_digest_invalid")


@dataclass(frozen=True)
class H3ModelPin:
    source_sha256: str
    checkpoint_sha256: str

    def __post_init__(self):
        _require_digest(self.source_sha256)
        _require_digest(self.checkpoint_sha256)


@dataclass(frozen=True)
class Nov30H3ForecastPins:
    data_source_sha256: str
    forecast_source_sha256: str
    self_model: H3ModelPin
    old60_model: H3ModelPin
    fit_sha256: str
    policy_sha256: str

    def __post_init__(self):
        for digest in (
            self.data_source_sha256,
            self.forecast_source_sha256,
            self.fit_sha256,
            self.policy_sha256,
        ):
            _require_digest(digest)
        if type(self.self_model) is not H3ModelPin or type(self.old60_model) is not H3ModelPin:
            raise ValueError("h3_forecast_model_pin_invalid")


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii")


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _identity(pins, ready_sha256, synthetic):
    _require_digest(ready_sha256)
    if type(synthetic) is not bool:
        raise ValueError("h3_forecast_mode_invalid")
    return dict(
        pins=asdict(pins),
        ready_sha256=ready_sha256,
        synthetic=synthetic,
        role=_ROLE,
        keys=list(_KEYS),
        context_close=_CLOSE.isoformat(),
        decision_at=NOV27_DECISION_UTC.isoformat(),
        entry_open=_ENTRY.isoformat(),
        expiry_open=_EXPIRY.isoformat(),
    )


def _utc(at):
    return type(at) is datetime and at.utcoffset() == timedelta(0)


def _vector(values):
    if len(values) != len(_KEYS) or any(
        type(value) is not float or not math.isfinite(value) for value in values
    ):
        raise ValueError("h3_forecast_vector_invalid")
    return list(values)


def _document(identity, verified, started, sealed, own, old):
    return dict(
        identity,
        schema="NOV30_FIXED_HALF_H3_FORECAST_V1",
        financial_authority=False,
        input_verified_at=verified.isoformat(),
        attempt_started_at=started.isoformat(),
        sealed_at=sealed.isoformat(),
        SELF=own,
        OLD60=old,
        BLEND=[0.5 * a + 0.5 * b for a, b in zip(own, old, strict=True)],
    )


def _attempt(identity, verified, started):
    return _json(
        dict(
            identity,
            schema="NOV30_FIXED_HALF_H3_ATTEMPT_V1",
            input_verified_at=verified.isoformat(),
            attempt_started_at=started.isoformat(),
        )
    )


def parse_nov30_h3_forecast(
    raw: bytes,
    attempt: bytes,
    *,
    pins: Nov30H3ForecastPins,
    ready_sha256: str,
    seal_sha256: str,
    synthetic: bool,
) -> dict:
    """Check a dated seal against independent pins and the successful runner's digest.

    Do not derive the expected digest from a discovered file: the runner can be
    interrupted after publication but before its final deadline check.
    """
    identity = _identity(pins, ready_sha256, synthetic)
    _require_digest(seal_sha256)
    if _sha(raw) != seal_sha256:
        raise ValueError("h3_forecast_seal_digest_mismatch")
    try:
        obj = json.loads(raw)
        verified, started, sealed = (
            datetime.fromisoformat(obj[key])
            for key in ("input_verified_at", "attempt_started_at", "sealed_at")
        )
        if (
            not all(map(_utc, (verified, started, sealed)))
            or not NOV27_CAPTURE_OPENS_UTC <= verified < NOV27_DECISION_UTC
            or not verified <= started <= sealed < _ENTRY
        ):
            raise ValueError("h3_forecast_clock_invalid")
        if attempt != _attempt(identity, verified, started):
            raise ValueError("h3_forecast_attempt_mismatch")
        expected = _document(
            dict(identity, attempt_sha256=_sha(attempt)),
            verified,
            started,
            sealed,
            _vector(obj["SELF"]),
            _vector(obj["OLD60"]),
        )
        if raw != _json(expected):
            raise ValueError("h3_forecast_seal_mismatch")
    except (KeyError, TypeError, OverflowError) as exc:
        raise ValueError("h3_forecast_seal_invalid") from exc
    return expected


def _check_input(arrays, header, identity):
    if (
        set(arrays) != _FIELDS
        or header["schema"] != "SHORT_SWING_H123_INPUT_V1"
        or header["producer"] != "Data.ShortSwingEndpointProducer"
        or header["consumer"] != "EngineResearch.ShortSwingHorizonInput"
        or header["source"] != identity["pins"]["data_source_sha256"]
        or header["role"] != _ROLE
        or header["synthetic"] is not identity["synthetic"]
        or header["unit"] != "ORIGINAL_LOG_OHLC_LAST_CLOSE_PLUS_IND8"
        or header["shape"] != [60, 12, 8]
        or (header["role_start"], header["role_stop"]) != (0, 1)
    ):
        raise ValueError("h3_forecast_input_schema_invalid")
    for field, shape, dtype in (
        ("x", (17, 60, 12), np.float32),
        ("z", (17, 8), np.float64),
        ("known", (17,), np.bool_),
        ("entry_index", (17,), np.int64),
    ):
        if arrays[field].shape != shape or arrays[field].dtype != dtype:
            raise ValueError("h3_forecast_input_axes_invalid")
    if (
        arrays["key"].tolist() != identity["keys"]
        or arrays["context_close"].tolist() != [identity["context_close"]] * 17
        or arrays["decision_at"].tolist() != [identity["decision_at"]] * 17
        or not arrays["known"].all()
        or arrays["entry_index"].any()
        or not np.isfinite(arrays["x"]).all()
        or not np.isfinite(arrays["z"]).all()
    ):
        raise ValueError("h3_forecast_input_cohort_invalid")


def _stage(path, raw):
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def _publish(pending, path):
    if os.name == "nt":
        from ctypes import WinDLL
        from ctypes.wintypes import BOOL, DWORD, LPCWSTR

        move = WinDLL("kernel32", use_last_error=True).MoveFileExW
        move.argtypes = (LPCWSTR, LPCWSTR, DWORD)
        move.restype = BOOL
        if not move(str(pending), str(path), 8):  # MOVEFILE_WRITE_THROUGH, no replace
            raise OSError("h3_forecast_publish_failed")
    else:
        os.link(pending, path)
        pending.unlink()
        for directory in (path.parent, path.parent.parent):
            fd = os.open(directory, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)


def seal_nov30_h3_forecast(
    destination: Path,
    produced: H3ProducedInput,
    *,
    pins: Nov30H3ForecastPins,
    clock: Callable[[], datetime],
    validate_input: Callable,
    forward: Callable[[str, H3ModelPin, str, Mapping[str, np.ndarray]], dict[str, float]],
) -> str:
    """Run SELF and OLD60 once in order; return the SHA-256 of the durable seal.

    One owned, prebound destination per slot. The caller attests the Data run,
    parser, clock, runtime and callback against source pins. The callback must
    verify the supplied model/FIT pins and return raw H3 means in exact key order.
    An interrupted attempt consumes the destination. A digest is not deployment
    or independent proof that the injected callback used the declared bytes.
    """
    if type(produced) is not H3ProducedInput or type(produced.binding) is not H3InputBinding:
        raise ValueError("h3_forecast_input_binding_invalid")
    binding = produced.binding
    if (
        binding.source_sha256 != pins.data_source_sha256
        or binding.decision_at != NOV27_DECISION_UTC
        or binding.hard_stop != NOV27_INPUT_HARD_STOP_UTC
    ):
        raise ValueError("h3_forecast_input_binding_invalid")
    identity = _identity(pins, produced.ready_sha256, binding.synthetic)
    if (
        not destination.is_absolute()
        or _safe_path(destination) != destination
        or any(
            destination.is_relative_to(root) or root.is_relative_to(destination)
            for root in (produced.input_root, produced.capture_state_path.parent)
        )
    ):
        raise ValueError("h3_forecast_destination_invalid")
    if destination.exists():
        raise FileExistsError("h3_forecast_destination_consumed")

    last = NOV27_CAPTURE_OPENS_UTC

    def checked_clock(cutoff=_ENTRY):
        nonlocal last
        now = clock()
        if not _utc(now) or not last <= now < cutoff:
            raise ValueError("h3_forecast_clock_invalid")
        last = now
        return now

    arrays, header = read_h3_publisher_input(
        produced.input_root,
        produced.capture_state_path,
        binding=binding,
        ready_sha256=produced.ready_sha256,
        clock=lambda: checked_clock(NOV27_DECISION_UTC),
        validate_input=validate_input,
    )
    _check_input(arrays, header, identity)
    verified = checked_clock(NOV27_DECISION_UTC)
    destination.mkdir(exist_ok=False)
    started = checked_clock()
    attempt = _attempt(identity, verified, started)
    attempt_path = destination / "ATTEMPT.json"
    _stage(destination / "ATTEMPT.pending", attempt)
    _publish(destination / "ATTEMPT.pending", attempt_path)

    vectors = []
    for name, pin in (("SELF", pins.self_model), ("OLD60", pins.old60_model)):
        # Independent immutable views keep one component from altering the other's input.
        inputs = MappingProxyType(
            {
                key: np.frombuffer(a.tobytes(), dtype=a.dtype).reshape(a.shape)
                for key, a in arrays.items()
            }
        )
        checked_clock()
        result = forward(name, pin, pins.fit_sha256, inputs)
        checked_clock()
        if type(result) is not dict or tuple(result) != _KEYS:
            raise ValueError("h3_forecast_output_order_invalid")
        vectors.append(_vector(result.values()))

    seal_path = destination / "SEAL.json"
    pending = destination / "SEAL.pending"
    raw = _json(
        _document(
            dict(identity, attempt_sha256=_sha(attempt)),
            verified,
            started,
            checked_clock(),
            *vectors,
        )
    )
    _stage(pending, raw)
    digest = _sha(raw)
    parse_nov30_h3_forecast(
        _read_native(destination, str(pending)),
        _read_native(destination, str(attempt_path)),
        pins=pins,
        ready_sha256=produced.ready_sha256,
        seal_sha256=digest,
        synthetic=binding.synthetic,
    )
    checked_clock()
    _publish(pending, seal_path)
    try:
        if _read_native(destination, str(seal_path)) != raw:
            raise ValueError("h3_forecast_published_bytes_changed")
        checked_clock()
    except Exception:
        seal_path.unlink(missing_ok=True)
        raise
    return digest

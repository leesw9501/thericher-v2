"""Seal the Dec4 CPU forecast for slot two of the prospective H3 study."""

from dataclasses import asdict
from datetime import UTC, datetime
from types import MappingProxyType, ModuleType

import numpy as np

from thericher_v2.models.h3_publisher_input import H3InputBinding, read_h3_publisher_input
from thericher_v2.ops import h3_dec4_point_owner as dec3
from thericher_v2.ops.h3_dec4_run import Dec4H3Run
from thericher_v2.ops.h3_nov30_run import _MEMBERS, POLICY_SHA256
from thericher_v2.research import nov30_h3_checkpoint_loader as loader
from thericher_v2.research.prospective_h3_forecast import (
    _KEYS as _LOADER_KEYS,
)
from thericher_v2.research.prospective_h3_forecast import (
    _publish,
    _require_digest,
    _stage,
    _vector,
)

STUDY = "h3-dec4-fixed-half-forecast-20261204-v1"
OPENS = datetime(2026, 12, 4, 14, 12, tzinfo=UTC)
LAST_START = OPENS.replace(minute=13)
HARD_STOP = OPENS.replace(minute=25)
CONTEXT_CLOSE = datetime(2026, 12, 3, 21, tzinfo=UTC)
ENTRY_OPEN = OPENS.replace(minute=30)
EXPIRY_OPEN = ENTRY_OPEN.replace(day=9)
ROLE = "FUTURE_20261203_ASOF_20261204"
KEYS = tuple(f"20261204|{i:02d}" for i in range(17))


def _make_forward(members):
    # The first-slot factory verifies all seven original byte pins and loads
    # the frozen statistics. Only the expected cohort keys differ for SELF.
    old60 = loader.make_nov30_h3_forward(**members)
    stats = loader._fit_stats(members["fit"])
    keys = np.array(_LOADER_KEYS)
    loader_keys = np.frombuffer(keys.tobytes(), dtype=keys.dtype)

    def forward(name, inputs):
        legacy = MappingProxyType(dict(inputs, key=loader_keys))
        if name == "OLD60":
            scores = old60(name, loader.OLD60_PIN, loader.FIT_SHA256, legacy)
            if tuple(scores) != _LOADER_KEYS:
                raise ValueError("dec4_fixed_half_output_order")
            return dict(zip(KEYS, scores.values(), strict=True))
        loader._check_arrays(legacy)
        values = loader._self_forward(
            inputs,
            members["self_source"],
            members["self_checkpoint"],
            members["input_adapter"],
            members["entry_io"],
            stats,
            keys=KEYS,
        )
        return dict(zip(KEYS, values.tolist(), strict=True))

    return forward


def run_dec4_fixed_half_forecast(*, forecast_source_sha256, clock, owner_ready, data_owner_closed):
    """Read only the named Dec3 features and return this attempt's seal digest.

    The isolated caller attests the source/runtime and owned output parent,
    provides a monotonic UTC wall clock and positively attests Dec3 process-tree
    closure for the exact PID, birth and receipt digest. It owns process timeouts.
    Future study admission must pin the returned digest and successful owner
    exit independently; a discovered SEAL.json is not completion evidence.
    """
    _require_digest(forecast_source_sha256)
    last = OPENS

    def checked_clock(cutoff=HARD_STOP):
        nonlocal last
        now = clock()
        if not dec3._is_utc(now) or not last <= now < cutoff:
            raise ValueError("dec4_fixed_half_clock")
        if owner_ready() is not True:
            raise ValueError("dec4_fixed_half_owner")
        last = now
        return now

    checked_clock(LAST_START)
    destination = dec3._RESEARCH / STUDY / "run"
    if not destination.is_absolute() or dec3._safe_path(destination) != destination:
        raise ValueError("dec4_fixed_half_destination")
    dec3._absent(destination)

    root = dec3._DATA / "run"
    run = Dec4H3Run(
        dec3._MARKET,
        root / "capture",
        root / "input",
        root / "point",
        dec3.DATA_SOURCE_SHA256,
        False,
    )
    # The point path is only the literal in the original DATA receipt. Do not
    # call point preflight or inspect any point/target custody.
    binding = H3InputBinding(run.data_source_sha256, HARD_STOP, dec3.INPUT_HARD_STOP_UTC, False)
    refs = dec3._read_data(run, binding, data_owner_closed)
    parser_raw = dec3._pinned(dec3._DATA / "source" / dec3._PARSER, dec3._PARSER_SHA, 16_384)
    parser = ModuleType("dec4_study_pinned_h123_contract")
    exec(
        compile(parser_raw, "<pinned Dec3 input contract>", "exec", dont_inherit=True),
        vars(parser),
    )
    arrays, header = read_h3_publisher_input(
        run.input_root,
        run.artifact_root / "capture-state.json",
        binding=binding,
        ready_sha256=refs[2],
        clock=lambda: checked_clock(LAST_START),
        validate_input=parser.validate_input,
    )
    if (
        header["role"] != ROLE
        or (header["role_start"], header["role_stop"]) != (0, 1)
        or arrays["key"].tolist() != list(KEYS)
        or arrays["context_close"].tolist() != [CONTEXT_CLOSE.isoformat()] * len(KEYS)
        or arrays["decision_at"].tolist() != [HARD_STOP.isoformat()] * len(KEYS)
    ):
        raise ValueError("dec4_fixed_half_cohort")
    verified = checked_clock(LAST_START)

    inputs = MappingProxyType(
        {k: np.frombuffer(a.tobytes(), dtype=a.dtype).reshape(a.shape) for k, a in arrays.items()}
    )
    forward = _make_forward(
        {name: dec3._read(path, 20 * 1024 * 1024) for name, path in _MEMBERS.items()}
    )

    def check_data():
        if dec3._read_data(run, binding, data_owner_closed) != refs:
            raise ValueError("dec4_fixed_half_data_changed")

    check_data()
    started = checked_clock(LAST_START)
    identity = dict(
        study=STUDY,
        financial_authority=False,
        synthetic=False,
        forecast_source_sha256=forecast_source_sha256,
        data_source_sha256=run.data_source_sha256,
        data_attempt_sha256=refs[0],
        data_owner_sha256=refs[1],
        ready_sha256=refs[2],
        data_ready_sha256=refs[3],
        parser_sha256=dec3._PARSER_SHA,
        self_model=asdict(loader.SELF_PIN),
        old60_model=asdict(loader.OLD60_PIN),
        fit_sha256=loader.FIT_SHA256,
        input_adapter_sha256=loader._ADAPTER_SHA256,
        entry_io_sha256=loader._ENTRY_IO_SHA256,
        policy_sha256=POLICY_SHA256,
        role=ROLE,
        keys=list(KEYS),
        context_close=CONTEXT_CLOSE.isoformat(),
        decision_at=HARD_STOP.isoformat(),
        entry_open=ENTRY_OPEN.isoformat(),
        expiry_open=EXPIRY_OPEN.isoformat(),
        input_verified_at=verified.isoformat(),
        attempt_started_at=started.isoformat(),
    )
    destination.mkdir(exist_ok=False)
    attempt = dec3._json(dict(identity, schema="DEC4_FIXED_HALF_H3_ATTEMPT_V1"))
    pending = destination / "ATTEMPT.pending"
    attempt_path = destination / "ATTEMPT.json"
    _stage(pending, attempt)
    checked_clock(LAST_START)
    _publish(pending, attempt_path)

    vectors = {}
    for name in ("SELF", "OLD60"):
        checked_clock(LAST_START if name == "SELF" else HARD_STOP)
        scores = forward(name, inputs)
        checked_clock()
        if type(scores) is not dict or tuple(scores) != KEYS:
            raise ValueError("dec4_fixed_half_output_order")
        vectors[name] = _vector(scores.values())
    check_data()
    own, old = vectors["SELF"], vectors["OLD60"]
    raw = dec3._json(
        dict(
            identity,
            schema="DEC4_FIXED_HALF_H3_FORECAST_V1",
            attempt_sha256=dec3._sha(attempt),
            sealed_at=checked_clock().isoformat(),
            BLEND=[0.5 * a + 0.5 * b for a, b in zip(own, old, strict=True)],
            **vectors,
        )
    )
    pending, seal_path = destination / "SEAL.pending", destination / "SEAL.json"
    _stage(pending, raw)
    if dec3._read(attempt_path) != attempt or dec3._read(pending) != raw:
        raise ValueError("dec4_fixed_half_writeback")
    checked_clock()
    _publish(pending, seal_path)
    try:
        if dec3._read(seal_path) != raw:
            raise ValueError("dec4_fixed_half_writeback")
        check_data()
        checked_clock()
    except Exception:
        seal_path.unlink(missing_ok=True)
        raise
    return dec3._sha(raw)

"""Admit only the completed Dec4 research forecast for the H3 block evaluator."""

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

from thericher_v2.data.kis_paper_h3_daily_panel import NET25_H3_AXIS
from thericher_v2.models.h3_publisher_input import H3InputBinding
from thericher_v2.ops import h3_dec4_fixed_half_plan as plan
from thericher_v2.ops import h3_dec4_point_owner as dec3
from thericher_v2.ops.h3_dec4_run import Dec4H3Run
from thericher_v2.research.prospective_h3_calendar import H3Interval
from thericher_v2.research.prospective_h3_forecast import _vector

RELEASE_AT = datetime(2026, 12, 28, 21, tzinfo=UTC)
INTERVAL = H3Interval(plan.ENTRY_OPEN.date(), plan.EXPIRY_OPEN.date())
_SYMBOLS = tuple(symbol for symbol, _ in NET25_H3_AXIS[: len(plan.KEYS)])
_MEMBERS = {"ATTEMPT.json", "SEAL.json"}


@dataclass(frozen=True)
class Dec4ForecastCompletion:
    """Independent supervisor evidence for the exact forecast owner tree."""

    source_sha256: str
    seal_sha256: str
    exit_code: int
    closed_at: datetime


@dataclass(frozen=True)
class Dec4FixedHalfForecast:
    interval: H3Interval
    forecast_symbols: tuple[str, ...]
    blend_scores: tuple[float, ...] = field(repr=False)


def _admit(attempt, seal, *, source, completion, refs):
    try:
        obj = json.loads(seal)
        verified, started, sealed = (
            dec3._stamp(obj[key])
            for key in ("input_verified_at", "attempt_started_at", "sealed_at")
        )
        own, old = (_vector(obj[key]) for key in ("SELF", "OLD60"))
    except (ValueError, KeyError, TypeError, OverflowError):
        raise ValueError("dec4_fixed_half_reader_record") from None
    if not (
        plan.OPENS <= verified <= started < plan.LAST_START
        and started <= sealed <= completion.closed_at < plan.HARD_STOP
    ):
        raise ValueError("dec4_fixed_half_reader_forecast_clock")
    identity = dict(
        study=plan.STUDY,
        financial_authority=False,
        synthetic=False,
        forecast_source_sha256=source,
        data_source_sha256=dec3.DATA_SOURCE_SHA256,
        data_attempt_sha256=refs[0],
        data_owner_sha256=refs[1],
        ready_sha256=refs[2],
        data_ready_sha256=refs[3],
        parser_sha256=dec3._PARSER_SHA,
        self_model=asdict(plan.loader.SELF_PIN),
        old60_model=asdict(plan.loader.OLD60_PIN),
        fit_sha256=plan.loader.FIT_SHA256,
        input_adapter_sha256=plan.loader._ADAPTER_SHA256,
        entry_io_sha256=plan.loader._ENTRY_IO_SHA256,
        policy_sha256=plan.POLICY_SHA256,
        role=plan.ROLE,
        keys=list(plan.KEYS),
        context_close=plan.CONTEXT_CLOSE.isoformat(),
        decision_at=plan.HARD_STOP.isoformat(),
        entry_open=plan.ENTRY_OPEN.isoformat(),
        expiry_open=plan.EXPIRY_OPEN.isoformat(),
        input_verified_at=verified.isoformat(),
        attempt_started_at=started.isoformat(),
    )
    if attempt != dec3._json(dict(identity, schema="DEC4_FIXED_HALF_H3_ATTEMPT_V1")):
        raise ValueError("dec4_fixed_half_reader_attempt")
    blend = tuple(0.5 * a + 0.5 * b for a, b in zip(own, old, strict=True))
    if seal != dec3._json(
        dict(
            identity,
            schema="DEC4_FIXED_HALF_H3_FORECAST_V1",
            attempt_sha256=dec3._sha(attempt),
            sealed_at=sealed.isoformat(),
            SELF=own,
            OLD60=old,
            BLEND=blend,
        )
    ):
        raise ValueError("dec4_fixed_half_reader_seal")
    return Dec4FixedHalfForecast(INTERVAL, _SYMBOLS, blend)


def read_dec4_fixed_half_forecast(
    *,
    forecast_source_sha256: str,
    completion: Dec4ForecastCompletion,
    data_owner_sha256: str,
    data_owner_closed: Callable[[int, str, str], bool],
    reader_ready: Callable[[], bool],
    clock: Callable[[], datetime],
) -> Dec4FixedHalfForecast:
    """Return score-only inputs for replay; the caller separately admits targets.

    The block launcher supplies the prebound forecast source and independent
    completion evidence: attested execution of that source, the returned digest
    (never a hash of a discovered seal) and successful full-tree exit before
    cutoff. The readiness probe attests one-shot authority, trusted clock,
    read-only isolation and no active/unknown writers to the relevant roots.
    The Data callback attests closure for the exact PID, birth and receipt.
    No forecast launcher, parser, model, target or market path is accessed.
    """
    if (
        type(completion) is not Dec4ForecastCompletion
        or not all(
            dec3._digest(value)
            for value in (
                forecast_source_sha256,
                completion.source_sha256,
                completion.seal_sha256,
                data_owner_sha256,
            )
        )
        or completion.source_sha256 != forecast_source_sha256
        or type(completion.exit_code) is not int
        or completion.exit_code != 0
        or not dec3._is_utc(completion.closed_at)
        or not plan.OPENS <= completion.closed_at < plan.HARD_STOP
    ):
        raise ValueError("dec4_fixed_half_reader_completion")
    last = RELEASE_AT

    def gate():
        nonlocal last
        now = clock()
        if not dec3._is_utc(now) or now < last or reader_ready() is not True:
            raise ValueError("dec4_fixed_half_reader_denied")
        last = now

    destination = dec3._RESEARCH / plan.STUDY / "run"
    root = dec3._DATA / "run"
    run = Dec4H3Run(
        dec3._MARKET,
        root / "capture",
        root / "input",
        root / "point",
        dec3.DATA_SOURCE_SHA256,
        False,
    )
    binding = H3InputBinding(
        run.data_source_sha256, plan.HARD_STOP, dec3.INPUT_HARD_STOP_UTC, False
    )
    paths = (
        destination / "ATTEMPT.json",
        destination / "SEAL.json",
        dec3._DATA / "source/SOURCE.json",
        root / "owner/ATTEMPT.json",
        root / "OWNER-CLOSED.json",
        run.input_root / "READY.json",
        run.input_root / "DATA-READY.json",
    )

    def fingerprint():
        if (
            not destination.is_absolute()
            or dec3._safe_path(destination) != destination
            or {path.name for path in destination.iterdir()} != _MEMBERS
        ):
            raise ValueError("dec4_fixed_half_reader_members")
        for marker in (
            root / "FAILED.json",
            run.input_root / "READY.pending",
            run.input_root / "DATA-READY.pending",
        ):
            dec3._absent(marker)
        result = []
        for path in (destination, *paths):
            if dec3._safe_path(path) != path:
                raise ValueError("dec4_fixed_half_reader_path")
            info = path.lstat()
            result.append((info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns))
        return result

    def attest_data(pid, birth, digest):
        return digest == data_owner_sha256 and data_owner_closed(pid, birth, digest) is True

    gate()
    before = fingerprint()
    seal = dec3._pinned(paths[1], completion.seal_sha256, 16_384)
    attempt = dec3._read(paths[0])
    refs = dec3._read_data(run, binding, attest_data)
    forecast = _admit(
        attempt, seal, source=forecast_source_sha256, completion=completion, refs=refs
    )
    gate()
    if (
        dec3._read_data(run, binding, attest_data) != refs
        or dec3._read(paths[0]) != attempt
        or dec3._read(paths[1]) != seal
    ):
        raise ValueError("dec4_fixed_half_reader_changed")
    gate()
    if fingerprint() != before:
        raise ValueError("dec4_fixed_half_reader_changed")
    return forecast

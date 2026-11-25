import json
import os
from dataclasses import asdict, replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from test_h3_dec4_point_owner import setup_owner  # noqa: F401
from thericher_v2.ops import h3_dec4_fixed_half_plan as plan
from thericher_v2.ops import h3_dec4_fixed_half_reader as reader
from thericher_v2.ops import h3_dec4_point_owner as dec3
from thericher_v2.research.prospective_h3_calendar import H3Interval

_SOURCE = "f" * 64
_SEALED = datetime(2026, 12, 4, 14, 14, tzinfo=UTC)
_CLOSED = _SEALED + timedelta(seconds=1)


@pytest.fixture
def case(setup_owner):  # noqa: F811
    box = setup_owner
    box.destination = dec3._RESEARCH / plan.STUDY / "run"
    box.destination.mkdir(parents=True)
    box.forecast_attempt = box.destination / "ATTEMPT.json"
    box.seal = box.destination / "SEAL.json"
    box.owner_pin = dec3._sha(box.closed_path.read_bytes())
    box.identity = dict(
        study="h3-dec4-fixed-half-forecast-20261204-v1",
        financial_authority=False,
        synthetic=False,
        forecast_source_sha256=_SOURCE,
        data_source_sha256=box.run.data_source_sha256,
        data_attempt_sha256=dec3._sha(box.attempt_path.read_bytes()),
        data_owner_sha256=box.owner_pin,
        ready_sha256=box.closed["ready_sha256"],
        data_ready_sha256=dec3._sha((box.run.input_root / "DATA-READY.json").read_bytes()),
        parser_sha256=dec3._PARSER_SHA,
        self_model=asdict(plan.loader.SELF_PIN),
        old60_model=asdict(plan.loader.OLD60_PIN),
        fit_sha256=plan.loader.FIT_SHA256,
        input_adapter_sha256=plan.loader._ADAPTER_SHA256,
        entry_io_sha256=plan.loader._ENTRY_IO_SHA256,
        policy_sha256=plan.POLICY_SHA256,
        role="FUTURE_20261203_ASOF_20261204",
        keys=[f"20261204|{i:02d}" for i in range(17)],
        context_close="2026-12-03T21:00:00+00:00",
        decision_at="2026-12-04T14:25:00+00:00",
        entry_open="2026-12-04T14:30:00+00:00",
        expiry_open="2026-12-09T14:30:00+00:00",
        input_verified_at="2026-12-04T14:12:00+00:00",
        attempt_started_at="2026-12-04T14:12:30+00:00",
    )

    def publish(*, identity=None, **seal_changes):
        identity = box.identity | (identity or {})
        attempt = dec3._json(dict(identity, schema="DEC4_FIXED_HALF_H3_ATTEMPT_V1"))
        seal = dict(
            identity,
            schema="DEC4_FIXED_HALF_H3_FORECAST_V1",
            attempt_sha256=dec3._sha(attempt),
            sealed_at=_SEALED.isoformat(),
            SELF=[float(i) for i in range(17)],
            OLD60=[-2.0] * 17,
            BLEND=[i / 2 - 1 for i in range(17)],
        )
        raw = dec3._json(seal | seal_changes)
        box.forecast_attempt.write_bytes(attempt)
        box.seal.write_bytes(raw)
        box.completion = reader.Dec4ForecastCompletion(_SOURCE, dec3._sha(raw), 0, _CLOSED)

    def attest(pid, birth, digest):
        proof = (pid, birth, digest)
        box.calls.append(proof)
        return proof == (box.attempt["pid"], box.closed["native_start"], box.owner_pin)

    def read(**updates):
        options = dict(
            forecast_source_sha256=_SOURCE,
            completion=box.completion,
            data_owner_sha256=box.owner_pin,
            data_owner_closed=attest,
            reader_ready=lambda: True,
            clock=lambda: reader.RELEASE_AT,
        )
        return reader.read_dec4_fixed_half_forecast(**(options | updates))

    box.publish, box.read = publish, read
    publish()
    return box


def test_native_readback_exposes_only_ordered_replay_inputs(case, monkeypatch):
    tracked = {
        case.forecast_attempt,
        case.seal,
        case.source,
        case.attempt_path,
        case.closed_path,
        case.ready_path,
        case.run.input_root / "DATA-READY.json",
    }
    before = {path: (path.stat().st_mtime_ns, path.read_bytes()) for path in tracked}
    seen = set()
    real_open, real_stat = Path.open, Path.lstat
    forbidden = (case.run.market_root, case.run.point_root, case.root / "target")

    def open_read_only(path, mode="r", *args, **kwargs):
        assert path in tracked and mode == "rb"
        seen.add(path)
        return real_open(path, mode, *args, **kwargs)

    def stat_metadata_only(path):
        assert not any(path.is_relative_to(root) for root in forbidden)
        assert path.name not in {"INPUT.npz", "INPUT.json", "capture-state.json", "contract.py"}
        return real_stat(path)

    with monkeypatch.context() as guard:
        guard.setattr(Path, "open", open_read_only)
        guard.setattr(Path, "lstat", stat_metadata_only)
        result = case.read()
    assert result.interval == H3Interval(date(2026, 12, 4), date(2026, 12, 9))
    assert result.forecast_symbols == tuple(
        "AAPL AMD AMZN GOOGL META MSFT NVDA TSLA JPM JNJ XOM PG KO HD V DIS UNH".split()
    )
    assert result.blend_scores == tuple(i / 2 - 1 for i in range(17))
    assert seen == tracked
    assert len(case.calls) == 2
    assert {path: (path.stat().st_mtime_ns, path.read_bytes()) for path in tracked} == before


@pytest.mark.parametrize(
    "changes",
    [
        {"exit_code": 1},
        {"exit_code": False},
        {"closed_at": _SEALED - timedelta(seconds=1)},
        {"closed_at": plan.HARD_STOP},
        {"closed_at": _CLOSED.replace(tzinfo=None)},
        {"source_sha256": "a" * 64},
        {"seal_sha256": "a" * 64},
    ],
)
def test_independent_completion_must_match(case, changes):
    with pytest.raises(ValueError):
        case.read(completion=replace(case.completion, **changes))


def test_discovered_seal_alone_is_not_completion(case):
    with pytest.raises(ValueError, match="reader_completion"):
        case.read(completion=None)


@pytest.mark.parametrize(
    "identity",
    [
        {"forecast_source_sha256": "a" * 64},
        {"data_source_sha256": "a" * 64},
        {"data_attempt_sha256": "a" * 64},
        {"data_owner_sha256": "a" * 64},
        {"ready_sha256": "a" * 64},
        {"data_ready_sha256": "a" * 64},
        {"parser_sha256": "a" * 64},
        {"self_model": {"source_sha256": "a" * 64, "checkpoint_sha256": "b" * 64}},
        {"old60_model": {"source_sha256": "a" * 64, "checkpoint_sha256": "b" * 64}},
        {"fit_sha256": "a" * 64},
        {"policy_sha256": "a" * 64},
        {"keys": list(reversed(plan.KEYS))},
        {"attempt_started_at": plan.LAST_START.isoformat()},
        {"input_verified_at": (plan.OPENS - timedelta(seconds=1)).isoformat()},
        {"synthetic": True},
        {"financial_authority": True},
    ],
)
def test_repinned_seal_cannot_change_frozen_identity(case, identity):
    case.publish(identity=identity)
    with pytest.raises(ValueError, match="dec4_fixed_half_reader_(attempt|forecast_clock)"):
        case.read()


@pytest.mark.parametrize(
    "changes",
    [
        {"BLEND": [0.0] * 17},
        {"BLEND": [0] * 17},
        {"SELF": [0.0] * 16},
        {"OLD60": [False] * 17},
        {"attempt_sha256": "a" * 64},
        {"sealed_at": plan.OPENS.isoformat()},
        {"schema": "DEC4_FROZEN_LSTM_H3_SHADOW_V2"},
    ],
)
def test_rejects_repinned_bad_seal(case, changes):
    case.publish(**changes)
    with pytest.raises(ValueError, match="dec4_fixed_half_reader_"):
        case.read()


def test_clock_and_authority_gate_before_any_read(case, monkeypatch):
    def deny(*args, **kwargs):
        pytest.fail("admission attempted filesystem access before its gate")

    with monkeypatch.context() as guard:
        guard.setattr(Path, "lstat", deny)
        with pytest.raises(ValueError, match="reader_denied"):
            case.read(clock=lambda: reader.RELEASE_AT - timedelta(microseconds=1))
        with pytest.raises(ValueError, match="reader_denied"):
            case.read(reader_ready=lambda: False)


def test_clock_must_not_roll_back_after_read(case):
    clock = iter((reader.RELEASE_AT + timedelta(seconds=1), reader.RELEASE_AT))
    with pytest.raises(ValueError, match="reader_denied"):
        case.read(clock=lambda: next(clock))


def test_data_must_be_independently_closed_and_pinned(case):
    with pytest.raises(ValueError, match="dec4_data_process_not_closed"):
        case.read(data_owner_closed=lambda *args: False)
    with pytest.raises(ValueError, match="dec4_data_process_not_closed"):
        case.read(data_owner_sha256="a" * 64)


@pytest.mark.parametrize("pending", ["ATTEMPT.pending", "SEAL.pending"])
def test_pending_artifact_withholds_admission(case, pending):
    (case.destination / pending).write_bytes(b"")
    with pytest.raises(ValueError, match="reader_members"):
        case.read()


def test_attempt_must_match_exact_bytes(case):
    attempt = json.loads(case.forecast_attempt.read_bytes())
    case.forecast_attempt.write_bytes(json.dumps(attempt).encode("ascii"))
    with pytest.raises(ValueError, match="reader_attempt"):
        case.read()


def test_same_bytes_rewritten_during_read_are_not_stable(case):
    def attest(*args):
        before = case.seal.stat()
        os.utime(case.seal, ns=(before.st_atime_ns, before.st_mtime_ns + 1_000_000_000))
        return True

    with pytest.raises(ValueError, match="reader_changed"):
        case.read(data_owner_closed=attest)


def test_late_data_pending_marker_withholds_admission(case):
    gates = iter((False, False, True))

    def ready():
        if next(gates):
            (case.run.input_root / "DATA-READY.pending").touch()
        return True

    with pytest.raises(FileExistsError, match="pending_or_consumed"):
        case.read(reader_ready=ready)

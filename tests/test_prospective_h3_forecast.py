import hashlib
import json
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import numpy as np
import pytest

from thericher_v2.data.kis_paper_h3_capture import H3DailyCapture
from thericher_v2.data.kis_paper_h3_daily_panel import (
    NET25_H3_AXIS,
    H3DailyPanel,
    H3DailyPanelPlan,
)
from thericher_v2.data.kis_paper_h3_producer import H3ProducedInput
from thericher_v2.execution.kis_market_data import KisPaperDailyRawRow
from thericher_v2.models.h3_publisher_input import H3InputBinding, write_h3_publisher_input
from thericher_v2.research import prospective_h3_forecast as forecast

DECISION = datetime(2026, 11, 30, 14, 25, tzinfo=UTC)
OPEN = datetime(2026, 11, 30, 14, 30, tzinfo=UTC)
CLOSE = datetime(2026, 11, 27, 18, tzinfo=UTC)
KEYS = tuple(f"20261130|{i:02d}" for i in range(17))
PINS = forecast.Nov30H3ForecastPins(
    "1" * 64,
    "2" * 64,
    forecast.H3ModelPin("3" * 64, "4" * 64),
    forecast.H3ModelPin("5" * 64, "6" * 64),
    "7" * 64,
    "8" * 64,
)


def _validate(arrays, header, *, expected_source, role, expected_keys, synthetic):
    assert header["source"] == expected_source == PINS.data_source_sha256
    assert header["role"] == role == "FUTURE_20261127_ASOF_20261130"
    assert header["synthetic"] is synthetic is True
    assert arrays["key"].tolist() == expected_keys == list(KEYS)


def _parse(root, **pins):
    header = json.loads((root / "INPUT.json").read_bytes())
    with np.load(root / "INPUT.npz", allow_pickle=False) as archive:
        arrays = dict(archive)
    _validate(arrays, header, **pins)
    return arrays, header


@pytest.fixture
def produced(tmp_path):
    plan = H3DailyPanelPlan(NET25_H3_AXIS, as_of=date(2026, 11, 27))
    panel = H3DailyPanel(
        plan,
        tuple(
            tuple(
                KisPaperDailyRawRow(day.strftime("%Y%m%d"), "2", "3", "1", "2", "1")
                for _ in NET25_H3_AXIS
            )
            for day in plan.sessions
        ),
    )
    capture_root = tmp_path / "capture"
    capture_root.mkdir()
    state = capture_root / "capture-state.json"
    state.write_bytes(b"invented closed state")
    closed = CLOSE + timedelta(minutes=35)
    capture = H3DailyCapture(panel, hashlib.sha256(state.read_bytes()).hexdigest(), closed)
    binding = H3InputBinding(PINS.data_source_sha256, DECISION, CLOSE + timedelta(minutes=45), True)
    root = tmp_path / "input"
    digest = write_h3_publisher_input(
        root,
        capture,
        binding=binding,
        clock=lambda: closed,
        prefix_features=lambda *_: (np.ones((17, 60, 12), np.float32), np.ones((17, 8))),
        parse_input=_parse,
    )
    return H3ProducedInput(root, state, binding, digest)


def _run(destination, produced, forward, *, clock=lambda: DECISION - timedelta(seconds=1)):
    return forecast.seal_nov30_h3_forecast(
        destination, produced, pins=PINS, clock=clock, validate_input=_validate, forward=forward
    )


def _scores(name):
    return {key: float(i if name == "SELF" else -2 * i) for i, key in enumerate(KEYS)}


def test_seals_once_from_ready_and_reparses_with_independent_pins(tmp_path, produced):
    destination = tmp_path / "forecast"
    calls = []

    def forward(name, model, fit, arrays):
        calls.append((name, model))
        assert fit == PINS.fit_sha256
        assert (destination / "ATTEMPT.json").is_file()
        assert not (destination / "SEAL.json").exists()
        assert arrays["x"].shape == (17, 60, 12)
        assert not arrays["x"].flags.writeable
        return _scores(name)

    digest = _run(destination, produced, forward)
    assert calls == [("SELF", PINS.self_model), ("OLD60", PINS.old60_model)]
    assert {p.name for p in destination.iterdir()} == {"ATTEMPT.json", "SEAL.json"}
    raw = (destination / "SEAL.json").read_bytes()
    attempt = (destination / "ATTEMPT.json").read_bytes()
    options = dict(
        pins=PINS, ready_sha256=produced.ready_sha256, seal_sha256=digest, synthetic=True
    )
    seal = forecast.parse_nov30_h3_forecast(raw, attempt, **options)
    assert digest == hashlib.sha256(raw).hexdigest()
    assert seal["keys"] == list(KEYS)
    assert seal["SELF"] == list(_scores("SELF").values())
    assert seal["OLD60"] == list(_scores("OLD60").values())
    assert seal["BLEND"] == [-0.5 * i for i in range(17)]
    assert seal["entry_open"] == OPEN.isoformat()
    assert seal["expiry_open"] == "2026-12-03T14:30:00+00:00"
    assert seal["financial_authority"] is False
    bad = forecast._json(dict(seal, BLEND=[0.0] * 17))
    with pytest.raises(ValueError, match="seal_digest_mismatch"):
        forecast.parse_nov30_h3_forecast(bad, attempt, **options)
    with pytest.raises(ValueError, match="seal_mismatch"):
        forecast.parse_nov30_h3_forecast(
            bad, attempt, **(options | {"seal_sha256": hashlib.sha256(bad).hexdigest()})
        )
    with pytest.raises(ValueError, match="attempt_mismatch"):
        forecast.parse_nov30_h3_forecast(
            raw, attempt, **(options | {"pins": replace(PINS, policy_sha256="9" * 64)})
        )
    with pytest.raises(FileExistsError, match="consumed"):
        _run(destination, produced, forward)
    assert len(calls) == 2


@pytest.mark.parametrize("case", ["ready", "capture", "decision", "binding"])
def test_input_refusal_never_consumes_attempt(tmp_path, produced, case):
    destination = tmp_path / "forecast"
    now = DECISION - timedelta(seconds=1)
    reason = {
        "ready": "ready_digest_mismatch",
        "capture": "member_digest_mismatch",
        "decision": "clock_invalid",
        "binding": "binding_invalid",
    }[case]
    if case == "ready":
        produced = replace(produced, ready_sha256="0" * 64)
    if case == "capture":
        produced.capture_state_path.write_bytes(b"substituted state")
    if case == "decision":
        now = DECISION
    if case == "binding":
        produced = replace(
            produced, binding=replace(produced.binding, hard_stop=CLOSE + timedelta(minutes=46))
        )
    with pytest.raises(ValueError, match=reason):
        _run(destination, produced, lambda *_: pytest.fail("forward called"), clock=lambda: now)
    assert not destination.exists()


@pytest.mark.parametrize("failure", ["callback", "order", "nonfinite", "open", "rollback"])
def test_failure_after_first_callback_consumes_without_seal(tmp_path, produced, failure):
    destination = tmp_path / "forecast"
    now = DECISION - timedelta(seconds=1)
    calls = []

    def forward(name, *_):
        nonlocal now
        calls.append(name)
        values = _scores(name)
        if failure == "callback":
            raise RuntimeError("invented failure")
        if failure == "order":
            return dict(reversed(tuple(values.items())))
        if failure == "nonfinite":
            values[KEYS[0]] = float("inf")
        if failure == "open":
            now = OPEN
        if failure == "rollback":
            now -= timedelta(seconds=1)
        return values

    with pytest.raises(RuntimeError if failure == "callback" else ValueError):
        _run(destination, produced, forward, clock=lambda: now)
    assert calls == ["SELF"]
    assert (destination / "ATTEMPT.json").is_file()
    assert not (destination / "SEAL.json").exists()
    with pytest.raises(FileExistsError, match="consumed"):
        _run(destination, produced, forward)


def test_publication_crossing_open_leaves_no_seal(tmp_path, produced, monkeypatch):
    destination = tmp_path / "forecast"
    now = DECISION - timedelta(seconds=1)
    publish = forecast._publish

    def publish_at_open(pending, path):
        nonlocal now
        publish(pending, path)
        if path.name == "SEAL.json":
            now = OPEN

    monkeypatch.setattr(forecast, "_publish", publish_at_open)

    def forward(name, *_):
        nonlocal now
        now = OPEN - timedelta(microseconds=1)
        return _scores(name)

    with pytest.raises(ValueError, match="clock_invalid"):
        _run(destination, produced, forward, clock=lambda: now)
    assert (destination / "ATTEMPT.json").is_file()
    assert not (destination / "SEAL.json").exists()
